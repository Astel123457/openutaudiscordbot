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


class StickyEmbedTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.directory.name)
        Path('config.json').write_text(json.dumps({'moderators': [123]}))
        with patch.dict(sys.modules, {'secretsd': SimpleNamespace(discord_token='fake', mistral_api_key='fake')}), patch('localization.export_custom'):
            self.bot = importlib.import_module('bot')

    async def asyncTearDown(self):
        await self.bot.client.close()
        sys.modules.pop('bot', None)
        os.chdir(self.old_cwd)
        self.directory.cleanup()

    async def test_create_with_and_without_header(self):
        for prepend in (True, False):
            with self.subTest(prepend=prepend):
                self.bot.sticky_messages.clear()
                modal = self.bot.CreateStickyMessageModal(prepend)
                modal.content.component._value = '**Please read**\nChannel guidelines'
                modal.repost_timeout.component._value = '00:30'
                channel = SimpleNamespace(id=456, send=AsyncMock(return_value=SimpleNamespace(id=789)))
                interaction = SimpleNamespace(channel=channel, response=AsyncMock())
                with patch.object(self.bot, 'tr', return_value='Created'):
                    await modal.on_submit(interaction)
                sent = channel.send.call_args
                self.assertEqual(sent.args, ())
                embed = sent.kwargs['embed']
                self.assertEqual(embed.description, '**Please read**\nChannel guidelines')
                self.assertEqual(embed.title, 'Stickied Message' if prepend else None)
                self.assertEqual(self.bot.sticky_messages['456']['timeout_seconds'], 30)
                self.assertEqual(self.bot.sticky_messages['456']['message_id'], 789)
                modal.stop()

    async def test_repost_preserves_saved_text_for_embed_and_deleted_messages(self):
        for missing in (False, True):
            with self.subTest(missing=missing):
                content = '__**Stickied Message:**__\n\nRemember the rules.'
                self.bot._save_sticky_message('456', {'content': content, 'message_id': 1, 'timeout_seconds': 0})
                self.bot.sticky_last_message_time['456'] = 100
                old_message = SimpleNamespace(content='', delete=AsyncMock())
                channel = SimpleNamespace(fetch_message=AsyncMock(return_value=old_message),
                                          send=AsyncMock(return_value=SimpleNamespace(id=2)))
                if missing:
                    channel.fetch_message.side_effect = discord.NotFound(SimpleNamespace(status=404, reason='Not Found'), 'Unknown Message')
                with patch.object(self.bot.asyncio, 'sleep', new=AsyncMock()):
                    await self.bot._do_sticky_repost('456', channel, 100)
                embed = channel.send.call_args.kwargs['embed']
                self.assertEqual(embed.title, 'Stickied Message')
                self.assertEqual(embed.description, 'Remember the rules.')
                saved = json.loads(Path('config.json').read_text())['sticky_messages']['456']
                self.assertEqual(saved['content'], content)
                self.assertEqual(saved['message_id'], 2)
                if not missing:
                    old_message.delete.assert_awaited_once()
