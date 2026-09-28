import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import discord

from changelog import Changelog, ChangelogError, GitHub, attachment_chunks, fetch_changelog, release_channel, send_changelog


def commit(number, message='A change'):
    return {'sha': f'{number:040x}', 'commit': {'message': message, 'author': {'name': 'Author', 'date': '2026-01-01'}}}


def release(tag, name='', prerelease=False, date='2026-01-01', **kwargs):
    return dict(tag_name=tag, name=name, prerelease=prerelease, published_at=date, **kwargs)


class ChangelogTests(unittest.IsolatedAsyncioTestCase):
    def test_split_attachments_preserve_unicode(self):
        data = ('変更 😀\n' * 50).encode('utf-8')
        chunks = list(attachment_chunks(data, 17))
        self.assertEqual(b''.join(chunks), data)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 17)
            chunk.decode('utf-8')

    async def test_default_compares_previous_to_current_release(self):
        api = GitHub(None)
        changes = [commit(122), commit(123)]
        api.get = AsyncMock(side_effect=[
            [release('0.1.565', date='2026-08-01'),
             release('0.1.570.12-alpha', prerelease=True, date='2026-09-28'),
             release('0.1.569-beta', prerelease=True, date='2026-09-20'),
             release('9.9.9', draft=True, date='2027-01-01')],
            commit(123), commit(121),
            {'status': 'ahead', 'commits': changes, 'total_commits': 2}])
        result = await api.changelog()
        self.assertEqual(result.label, '0.1.569-beta → 0.1.570.12-alpha')
        self.assertEqual(result.commits, changes)
        self.assertEqual(api.get.await_args_list[1].args[0], '/commits/0.1.570.12-alpha')
        self.assertEqual(api.get.await_args_list[2].args[0], '/commits/0.1.569-beta')
        self.assertNotIn('/commits/master', [call.args[0] for call in api.get.await_args_list])

    async def test_default_requires_two_releases(self):
        api = GitHub(None)
        api.get = AsyncMock(return_value=[release('0.1.565')])
        with self.assertRaisesRegex(ChangelogError, 'previous published release'):
            await api.changelog()

    async def test_default_without_releases_reports_error(self):
        api = GitHub(None)
        api.get = AsyncMock(return_value=[])
        with self.assertRaisesRegex(ChangelogError, 'No published'):
            await api.changelog()

    async def test_channels_and_versions_with_historical_tags(self):
        releases = [release('0.1.570.12-alpha', prerelease=True, date='2026-09-28'),
                    release('0.1.569-beta', '0.1.569 Beta', True, date='2026-09-20'),
                    release('0.1.568', '0.1.568 Beta', True),
                    release('0.1.565', date='2026-08-01'),
                    release('build/0.1.539', '0.1.539 Beta', True),
                    release('9.9.9', draft=True, date='2027-01-01')]
        api = GitHub(None)
        api.get = AsyncMock(return_value=releases)
        for selector, tag in [('alpha', '0.1.570.12-alpha'), ('beta', '0.1.569-beta'),
                              ('stable', '0.1.565'), ('v0.1.569', '0.1.569-beta'),
                              ('0.1.539', 'build/0.1.539'), ('0.1.568', '0.1.568')]:
            with self.subTest(selector=selector):
                self.assertEqual((await api.release(selector))['tag_name'], tag)
        self.assertEqual(release_channel(release('0.1.568', '0.1.568 Beta')), 'beta')

    async def test_all_release_pages_and_publication_order(self):
        api = GitHub(None)
        api.get = AsyncMock(side_effect=[
            [release(f'0.1.{i}-alpha', prerelease=True) for i in range(99)] + [release('0.1.500')],
            [release('0.1.501', date='2026-02-01')]])
        self.assertEqual((await api.release('stable'))['tag_name'], '0.1.501')
        api.get.assert_awaited_with('/releases', per_page=100, page=2)

    async def test_compare_paginates_and_pins_both_commits(self):
        api = GitHub(None)
        api.release = AsyncMock(side_effect=[release('0.1.570.12-alpha'), release('build/0.1.539')])
        commits = [commit(i) for i in range(1, 252)]
        api.get = AsyncMock(side_effect=[commit(999), commit(0)] + [
            {'status': 'ahead', 'commits': commits[i:i+100], 'total_commits': len(commits)}
            for i in range(0, len(commits), 100)])
        result = await api.changelog(' 0.1.539 ')
        self.assertEqual(result.commits, commits)
        self.assertEqual(api.get.await_args_list[0].args[0], '/commits/0.1.570.12-alpha')
        self.assertEqual(api.get.await_args_list[1].args[0], '/commits/build%2F0.1.539')
        path = f"/compare/{commit(0)['sha']}...{commit(999)['sha']}"
        api.get.assert_awaited_with(path, per_page=100, page=3)
        self.assertTrue(result.url.endswith(path.removeprefix('/compare')))

    async def test_empty_and_diverged_comparisons(self):
        for status in ('identical', 'behind', 'diverged'):
            api = GitHub(None)
            api.release = AsyncMock(return_value=release('0.1.565'))
            api.get = AsyncMock(side_effect=[commit(10), commit(10),
                {'status': status, 'commits': [], 'total_commits': 0}])
            if status == 'identical':
                self.assertEqual((await api.changelog('stable')).commits, [])
            else:
                with self.assertRaises(ChangelogError):
                    await api.changelog('stable')

    async def test_invalid_and_missing_versions(self):
        api = GitHub(None)
        api.get = AsyncMock(return_value=[])
        for value in ('../master', 'nightly', '0.579.0'):
            with self.assertRaises(ChangelogError):
                await api.release(value)
        self.assertEqual(api.get.await_count, 1)

    async def test_http_failures(self):
        for status in (403, 404, 429, 500):
            response = AsyncMock(status=status)
            response.__aenter__.return_value = response
            session = SimpleNamespace(get=lambda *args, **kwargs: response)
            with self.assertRaises(ChangelogError):
                await GitHub(session).get('/commits/master')

    async def test_timeout_becomes_friendly_error(self):
        with patch.object(GitHub, 'changelog', side_effect=TimeoutError):
            with self.assertRaisesRegex(ChangelogError, 'in time'):
                await fetch_changelog()

    async def test_large_output_preserves_full_messages_and_bounds_pages(self):
        commits = [commit(i, '@everyone **subject**\n\n' + 'Detailed change\n' * 100) for i in range(300)]
        result = Changelog('Since 0.1.565', 'https://example.com', 'a' * 40, commits)
        pages = result.pages()
        self.assertGreater(len(pages), 1)
        self.assertTrue(all(len(page) <= 3500 for page in pages))
        self.assertNotIn('@everyone', ''.join(pages))
        self.assertEqual(result.attachment().decode().count('Detailed change'), 30000)
        for c in commits:
            self.assertEqual(''.join(pages).count('/commit/' + c['sha']), 1)

    async def test_send_and_navigation(self):
        interaction = SimpleNamespace(response=AsyncMock(), followup=AsyncMock(), guild=None,
                                      user=SimpleNamespace(id=1), locale=discord.Locale.american_english)
        result = Changelog('Since 0.1.565', 'https://example.com', 'f' * 40,
                           [commit(i) for i in range(100)])
        with patch('changelog.fetch_changelog', return_value=result):
            await send_changelog(interaction)
        interaction.response.defer.assert_awaited_once_with(thinking=True)
        sent = interaction.followup.send.call_args.kwargs
        self.assertEqual(sent['files'][0].fp.getvalue(), result.attachment())
        view = sent['view']
        self.assertTrue(view.previous.disabled)
        self.assertFalse(view.next.disabled)
        click = SimpleNamespace(user=SimpleNamespace(id=1), response=AsyncMock())
        self.assertTrue(await view.interaction_check(click))
        await view.next.callback(click)
        self.assertEqual(view.index, 1)
        click.response.edit_message.assert_awaited_once()
        click.user.id = 2
        self.assertFalse(await view.interaction_check(click))
        await view.on_timeout()
        self.assertTrue(all(b.disabled for b in view.children))
        view.stop()

    async def test_send_error_has_no_attachment(self):
        interaction = SimpleNamespace(response=AsyncMock(), followup=AsyncMock())
        with patch('changelog.fetch_changelog', side_effect=ChangelogError('Try again')):
            await send_changelog(interaction, 'stable')
        interaction.followup.send.assert_awaited_once()
        self.assertEqual(interaction.followup.send.call_args.args, ('Try again',))
        self.assertNotIn('files', interaction.followup.send.call_args.kwargs)
