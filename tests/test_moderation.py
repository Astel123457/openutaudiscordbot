import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
from discord.ext import commands
from mistralai.client.models import ModerationResponse

from moderation import MODEL, register_moderation, report_message


def response(categories, scores=None):
    return ModerationResponse.model_validate({'id': 'test', 'model': MODEL,
        'results': [{'categories': categories, 'category_scores': scores or {}}]})


class ModerationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.message = SimpleNamespace(id=123, content='Example text', reply=AsyncMock(),
                                       channel=SimpleNamespace(id=456), author=SimpleNamespace(id=789))
        self.mistral = SimpleNamespace(classifiers=SimpleNamespace(moderate_async=AsyncMock()))

    async def test_disabled_and_empty_do_not_call_api(self):
        await report_message(self.message, self.mistral, lambda: False)
        self.message.content = ' '
        await report_message(self.message, self.mistral, lambda: True)
        self.mistral.classifiers.moderate_async.assert_not_awaited()
        self.message.reply.assert_not_awaited()

    async def test_unflagged_is_silent_even_with_nonzero_scores(self):
        self.mistral.classifiers.moderate_async.return_value = response({'violence': False}, {'violence': .4})
        await report_message(self.message, self.mistral, lambda: True)
        self.message.reply.assert_not_awaited()

    async def test_reports_only_flagged_categories_with_no_ping_or_action(self):
        self.mistral.classifiers.moderate_async.return_value = response(
            {'violence': True, 'hate_and_discrimination': True, 'sexual': False}, {'violence': .95})
        await report_message(self.message, self.mistral, lambda: True)
        self.mistral.classifiers.moderate_async.assert_awaited_once_with(
            model=MODEL, inputs='Example text', timeout_ms=15000)
        kwargs = self.message.reply.call_args.kwargs
        self.assertIn('violence (score: 0.950)', kwargs['embed'].description)
        self.assertIn('hate', kwargs['embed'].description)
        self.assertNotIn('sexual', kwargs['embed'].description)
        self.assertFalse(kwargs['mention_author'])
        self.assertTrue(kwargs['silent'])
        self.assertEqual(kwargs['allowed_mentions'].to_dict(), {'parse': []})

    async def test_disable_during_request_prevents_reply(self):
        self.mistral.classifiers.moderate_async.return_value = response({'violence': True})
        await report_message(self.message, self.mistral, Mock(side_effect=[True, False]))
        self.message.reply.assert_not_awaited()

    async def test_api_failure_and_bad_response_do_not_reply_or_raise(self):
        for value in (RuntimeError('private message'), SimpleNamespace(results=[])):
            call = self.mistral.classifiers.moderate_async
            call.side_effect = value if isinstance(value, Exception) else None
            call.return_value = value
            with self.assertLogs('moderation', level='WARNING') as logs:
                await report_message(self.message, self.mistral, lambda: True)
            self.assertNotIn('private message', ''.join(logs.output))
        self.message.reply.assert_not_awaited()

    async def test_prefix_channel_configuration_and_listener(self):
        client = commands.Bot(command_prefix='!', intents=discord.Intents.none())
        config = {'moderators': [789]}
        save = Mock()
        register_moderation(client, self.mistral, lambda: config, save)
        command = client.get_command('moderation')
        ctx = SimpleNamespace(author=self.message.author, channel=self.message.channel, send=AsyncMock())
        listener = client.extra_events['on_message'][0]
        try:
            await listener(self.message)
            self.mistral.classifiers.moderate_async.assert_not_awaited()
            await command.callback(ctx, 'on')
            self.assertEqual(config['moderation_channels'], ['456'])
            save.assert_called_once()
            await command.callback(ctx, 'status')
            save.assert_called_once()
            self.mistral.classifiers.moderate_async.return_value = response({'violence': True})
            await listener(self.message)
            self.message.reply.assert_awaited_once()
            self.message.author = client.user
            await listener(self.message)
            self.mistral.classifiers.moderate_async.assert_awaited_once()
            ctx.author = SimpleNamespace(id=999)
            await command.callback(ctx, 'off')
            self.assertEqual(config['moderation_channels'], ['456'])
            ctx.author = SimpleNamespace(id=789)
            await command.callback(ctx, 'off')
            self.assertEqual(config['moderation_channels'], [])
            self.assertEqual(save.call_count, 2)
        finally:
            await client.close()
