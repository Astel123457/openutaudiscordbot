import asyncio
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import discord
from discord import app_commands

from localization import Catalog, ROOT, custom_key, custom_sources, export_custom, write_json
from localization_sync import validate
from translations import MyTranslator, localized


class LocalizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        write_json(self.root / 'translations/en.json', {'greeting': 'Hello {name}'})
        self.config = {'faq': {'info': 'Original answer', 'has_image': False},
                       'moderators': [123], 'channel_languages': {'123': 'ja'},
                       'sticky_messages': {'123': {'content': 'Private note'}}}

    def catalog(self, translations):
        write_json(self.root / 'translations/custom/ja.json', translations)
        return Catalog(self.root)

    def test_export_includes_only_command_name_and_info(self):
        sources = export_custom(self.config, self.root)
        self.assertEqual(set(sources.values()), {'faq', 'Original answer'})
        self.assertEqual(json.loads((self.root / 'translations/custom/en.json').read_text()), sources)

    def test_edited_deleted_and_renamed_answers_do_not_reuse_translations(self):
        key = custom_key('faq', 'info', 'Original answer')
        catalog = self.catalog({key: '承認済みの回答'})
        self.assertEqual(catalog.custom_text('faq', 'info', 'Original answer', 'ja'), '承認済みの回答')
        self.assertEqual(catalog.custom_text('faq', 'info', 'Edited answer', 'ja'), 'Edited answer')
        self.assertEqual(catalog.custom_text('renamed', 'info', 'Original answer', 'ja'), 'Original answer')
        self.config.pop('faq')
        self.assertEqual(custom_sources(self.config), {})

    def test_locale_fallback_and_draft_not_loaded(self):
        catalog = self.catalog({custom_key('faq', 'info', 'Original answer'): '日本語'})
        self.assertEqual(catalog.custom_text('faq', 'info', 'Original answer', 'fr'), 'Original answer')
        write_json(self.root / 'translations/drafts/ja.json', {'greeting': 'こんにちは {name}'})
        self.assertEqual(catalog.text('greeting', discord.Locale.japanese, name='A'), 'Hello A')

    def test_bad_placeholders_fall_back(self):
        write_json(self.root / 'translations/ja.json', {'greeting': 'Hello {other}'})
        self.assertEqual(Catalog(self.root).text('greeting', 'ja', name='A'), 'Hello A')
        with self.assertRaises(ValueError):
            validate({'greeting': 'Hello {name}'}, {'greeting': 'Hello {other}'})

    def test_ambiguous_aliases_and_reserved_names_are_ignored(self):
        self.config['help'] = {'info': 'Help'}
        values = {custom_key('faq', 'name', 'faq'): '質問', custom_key('help', 'name', 'help'): '質問'}
        self.assertEqual(self.catalog(values).aliases(self.config, 'ja'), {})
        values[custom_key('help', 'name', 'help')] = 'sync'
        self.assertEqual(self.catalog(values).aliases(self.config, 'ja', reserved={'sync'}), {'質問': 'faq'})

    def test_failed_download_does_not_replace_released_catalogs(self):
        import localization_sync
        write_json(self.root / 'config.json', self.config)
        write_json(self.root / 'translations/ja.json', {'greeting': 'Existing'})
        with patch.object(localization_sync, 'ROOT', self.root), patch.object(sys, 'argv', ['sync', 'download']), patch.object(localization_sync.subprocess, 'run', side_effect=RuntimeError('offline')):
            with self.assertRaises(RuntimeError):
                localization_sync.main()
        self.assertEqual(json.loads((self.root / 'translations/ja.json').read_text()), {'greeting': 'Existing'})

    def test_download_requests_only_approved_and_releases_valid_catalog(self):
        import localization_sync
        write_json(self.root / 'config.json', self.config)
        def download(args, **kwargs):
            self.assertIn('--export-only-approved', args)
            self.assertIn('--skip-untranslated-strings', args)
            stage = Path(args[args.index('--base-path') + 1])
            write_json(stage / 'translations/ja/en.json', {'greeting': 'こんにちは {name}'})
            write_json(stage / 'translations/custom/ja/en.json', {})
        with patch.object(localization_sync, 'ROOT', self.root), patch.object(sys, 'argv', ['sync', 'download']), patch.object(localization_sync.subprocess, 'run', side_effect=download):
            localization_sync.main()
        self.assertEqual(json.loads((self.root / 'translations/ja.json').read_text()), {'greeting': 'こんにちは {name}'})


class BotRegistrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_registration_translation_and_modal_without_connecting(self):
        with tempfile.TemporaryDirectory() as directory:
            old = os.getcwd()
            try:
                os.chdir(directory)
                write_json(Path('config.json'), {'moderators': [123], 'faq': {'info': 'Answer'}})
                with patch.dict(sys.modules, {'secretsd': SimpleNamespace(discord_token='fake', mistral_api_key='fake')}), patch('localization.export_custom'):
                    bot = importlib.import_module('bot')
                try:
                    for command in bot.client.tree.get_commands():
                        self.assertFalse(command.description.startswith('commands.'))
                        self.assertLessEqual(len(command.description), 100)
                        await command.get_translated_payload(bot.client.tree, MyTranslator())
                    interaction = SimpleNamespace(locale=discord.Locale.japanese)
                    modal = bot.localize_modal(bot.MakeCommandModal(), interaction)
                    self.assertEqual(modal.title, 'Create a Custom Command')
                    self.assertEqual(bot.command_list, ['faq'])
                    self.assertEqual(str(localized('commands.stop.description')), 'Stops the AI conversation in the current channel.')
                    bot.config['channel_languages'] = {'456': 'ja'}
                    bot.channel_command_cooldowns['456'] = 0
                    message = SimpleNamespace(author=object(), content='!質問', channel=SimpleNamespace(id=456, send=AsyncMock()))
                    translations = {custom_key('faq', 'name', 'faq'): '質問', custom_key('faq', 'info', 'Answer'): '回答'}
                    with patch.dict(bot.catalog.custom, {'ja': translations}):
                        await bot.on_message(message)
                        message.channel.send.assert_awaited_with('回答')
                        bot.config['faq']['info'] = 'Updated answer'
                        message.content = '!faq'
                        await bot.on_message(message)
                        message.channel.send.assert_awaited_with('Updated answer')
                    await bot.client.close()
                finally:
                    sys.modules.pop('bot', None)
            finally:
                os.chdir(old)
