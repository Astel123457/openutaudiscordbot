import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord

from reaction_delete import register_reaction_delete


class ReactionDeleteTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.message = SimpleNamespace(author=SimpleNamespace(id=1), delete=AsyncMock())
        self.channel = SimpleNamespace(fetch_message=AsyncMock(return_value=self.message))
        self.client = SimpleNamespace(user=SimpleNamespace(id=1),
                                      get_channel=Mock(return_value=self.channel),
                                      fetch_channel=AsyncMock(return_value=self.channel))
        def listen(event):
            self.assertEqual(event, 'on_raw_reaction_add')
            def register(callback):
                self.callback = callback
                return callback
            return register
        self.client.listen = listen
        self.config = {'moderators': [2]}
        register_reaction_delete(self.client, lambda: self.config)
        self.payload = SimpleNamespace(user_id=2, channel_id=3, message_id=4,
                                       emoji=discord.PartialEmoji(name='❌'))

    async def test_moderator_can_dismiss_bot_message(self):
        await self.callback(self.payload)
        self.message.delete.assert_awaited_once()

    async def test_uncached_channel_and_message(self):
        self.client.get_channel.return_value = None
        await self.callback(self.payload)
        self.client.fetch_channel.assert_awaited_once_with(3)
        self.channel.fetch_message.assert_awaited_once_with(4)
        self.message.delete.assert_awaited_once()

    async def test_other_authors_are_not_deleted(self):
        self.message.author.id = 99
        await self.callback(self.payload)
        self.message.delete.assert_not_awaited()

    async def test_own_reactions_other_emoji_and_custom_emoji_ignored(self):
        self.payload.user_id = 1
        await self.callback(self.payload)
        self.payload.user_id = 2
        for emoji in (discord.PartialEmoji(name='👍'), discord.PartialEmoji(name='x', id=99)):
            self.payload.emoji = emoji
            await self.callback(self.payload)
        self.channel.fetch_message.assert_not_awaited()

    async def test_missing_message_and_permissions_are_handled(self):
        self.channel.fetch_message.side_effect = discord.NotFound(SimpleNamespace(status=404, reason='Not Found'), '')
        await self.callback(self.payload)
        self.channel.fetch_message.side_effect = None
        self.message.delete.side_effect = discord.Forbidden(SimpleNamespace(status=403, reason='Forbidden'), '')
        with self.assertLogs('reaction_delete', level='WARNING'):
            await self.callback(self.payload)

    async def test_nonmoderator_cannot_fetch_or_delete(self):
        self.payload.user_id = 99
        await self.callback(self.payload)
        self.channel.fetch_message.assert_not_awaited()
        self.message.delete.assert_not_awaited()

    async def test_permissions_follow_current_config(self):
        self.config['moderators'] = []
        await self.callback(self.payload)
        self.channel.fetch_message.assert_not_awaited()
        self.config['moderators'] = [2]
        await self.callback(self.payload)
        self.message.delete.assert_awaited_once()

    async def test_revoked_permission_during_fetch_prevents_delete(self):
        async def fetch(message_id):
            self.config['moderators'] = []
            return self.message
        self.channel.fetch_message.side_effect = fetch
        await self.callback(self.payload)
        self.message.delete.assert_not_awaited()
