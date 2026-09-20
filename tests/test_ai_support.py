import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
from mistralai.client.models import CompletionEvent
from mistralai.client.utils.eventstreaming import EventStreamAsync

from ai_support import DiscordReply, HelpTools, stream_answer


class Message:
    def __init__(self, content):
        self.content = content
        self.deleted = False

    async def edit(self, *, content):
        assert 0 < len(content) <= 2000
        self.content = content

    async def delete(self):
        self.deleted = True


class Channel:
    def __init__(self):
        self.messages = []

    async def send(self, content):
        assert 0 < len(content) <= 2000
        message = Message(content)
        self.messages.append(message)
        return message

    def text(self):
        return ''.join(m.content for m in self.messages if not m.deleted)


class Bytes(httpx.AsyncByteStream):
    def __init__(self, data):
        self.data = data

    async def __aiter__(self):
        yield self.data


def event(delta, finish=None):
    return {'id': 'test', 'object': 'chat.completion.chunk', 'created': 1,
            'model': 'mistral-medium-latest',
            'choices': [{'index': 0, 'delta': delta, 'finish_reason': finish}]}


class Chat:
    def __init__(self, rounds):
        self.rounds = iter(rounds)
        self.requests = []
        self.responses = []

    async def stream_async(self, **kwargs):
        self.requests.append(copy.deepcopy(kwargs))
        data = ''.join('data: ' + json.dumps(e) + '\n\n' for e in next(self.rounds))
        response = httpx.Response(200, stream=Bytes(data.encode()))
        self.responses.append(response)
        return EventStreamAsync(response, CompletionEvent.model_validate_json, sentinel='[DONE]')


def call(index, name, args, identifier='null'):
    return {'index': index, 'id': identifier, 'type': 'function',
            'function': {'name': name, 'arguments': args}}


class Tests(unittest.IsolatedAsyncioTestCase):
    async def test_lossless_rollover_between_preview_edits(self):
        source = 'Intro\n' * 300 + 'This Phonemizer is designed to support many different singers.\n' * 80
        for size in (1, 17, 1997, 2000, 7000):
            with self.subTest(size=size):
                channel = Channel()
                reply = DiscordReply(channel)
                await reply.start()
                for pos in range(0, len(source), size):
                    await reply.append(source[pos:pos + size])
                await reply.finish()
                self.assertEqual(channel.text(), source)
                self.assertEqual(reply.full_text, source)

    async def test_long_unbroken_text_and_stop_suffix(self):
        channel = Channel()
        reply = DiscordReply(channel)
        await reply.start()
        source = '界😀' * 3500 + '\n-- (AI was Stopped by command)'
        await reply.append(source)
        await reply.finish()
        self.assertEqual(channel.text(), source)

    async def test_commands_searches_content_excludes_settings_and_reads_updates(self):
        config = {'faq': {'info': 'Install a phonemizer', 'image': '/private/path'},
                  'moderators': [123], 'sticky_messages': {'info': 'private'},
                  'channel_command_cooldowns': {}, 'stickynotes': {'info': 'private'}}
        tools = HelpTools(lambda: config, [])
        result = json.loads(await tools.execute('search_commands', {'query': 'phonemizer'}))
        self.assertEqual(result['results'], [{'command': '!faq', 'info': 'Install a phonemizer', 'has_image': True}])
        config['new'] = {'info': 'Updated answer'}
        result = json.loads(await tools.execute('search_commands', {'query': ''}))
        self.assertEqual(result['total'], 2)

    async def test_wiki_search_read_pagination_errors(self):
        tools = HelpTools(lambda: {}, [])
        tools.fetch = AsyncMock(return_value='<a href="/openutau/OpenUtau/wiki/Getting-Started">Start</a>')
        result = json.loads(await tools.execute('search_wiki', {'query': 'getting'}))
        self.assertEqual(result['results'][0]['page'], 'Getting-Started')
        tools.fetch.return_value = 'x' * 12001
        result = json.loads(await tools.execute('read_wiki_page', {'page': 'Getting-Started'}))
        self.assertEqual(result['next_offset'], 12000)
        result = json.loads(await tools.execute('read_wiki_page', {'page': 'Getting-Started', 'offset': 12000}))
        self.assertEqual(result['content'], 'x')
        self.assertIsNone(result['next_offset'])
        for name, args in [('read_wiki_page', {'page': '../secrets'}),
                           ('search_commands', '{bad json'), ('search_commands', {'query': '', 'offset': -1}),
                           ('unknown', {'query': ''})]:
            self.assertIn('error', json.loads(await tools.execute(name, args)))
        tools.fetch.side_effect = OSError('unavailable')
        self.assertIn('error', json.loads(await tools.execute('search_wiki', {'query': ''})))

    async def test_fragmented_parallel_tools_followup_and_sdk_stream_cleanup(self):
        chat = Chat([
            [event({'tool_calls': [call(0, 'search_commands', '{"query":', 'abcdef123'),
                                   call(1, 'search_wiki', '{"query":"install"}', 'abcdef456')]}),
             event({'tool_calls': [call(0, '', '"install"}')]}),
             event({}, 'tool_calls')],
            [event({'tool_calls': [call(0, 'read_wiki_page', '{"page":"Install"}', 'abcdef789')]}),
             event({}, 'tool_calls')],
            [event({}, 'stop')],
            [event({'content': 'Use !install. ' + 'Helpful wiki answer. ' * 200}), event({}, 'stop')]])
        tools = HelpTools(lambda: {'install': {'info': 'Install OpenUtau'}}, [])
        tools.fetch = AsyncMock(return_value='<a href="/openutau/OpenUtau/wiki/Install">Install</a>')
        channel = Channel()
        reply = DiscordReply(channel)
        await reply.start()
        history = [{'role': 'system', 'content': 'Help'}, {'role': 'user', 'content': 'How to install?'}]
        await stream_answer(SimpleNamespace(chat=chat), history, reply, tools, lambda: False)
        exchange = chat.requests[1]['messages']
        self.assertEqual([m['role'] for m in exchange], ['system', 'user', 'assistant', 'tool', 'tool'])
        self.assertEqual(exchange[3]['tool_call_id'], 'abcdef123')
        self.assertIn('!install', exchange[3]['content'])
        self.assertEqual(history[-1]['content'], channel.text())
        self.assertEqual(len(chat.requests), 4)
        self.assertTrue(all(r.is_closed for r in chat.responses))

    async def test_lookup_prose_and_simulated_calls_never_reach_discord(self):
        narration = 'I will search now. search_wiki("close tips menu") No results found.'
        for actual_call in (True, False):
            with self.subTest(actual_call=actual_call):
                lookup = [event({'content': narration})]
                if actual_call:
                    lookup += [event({'tool_calls': [call(0, 'search_commands', '{"query":"tips"}', 'abcdef123')]}),
                               event({}, 'tool_calls')]
                    rounds = [lookup, [event({}, 'stop')]]
                else:
                    rounds = [lookup + [event({}, 'stop')]]
                rounds.append([event({'content': 'The available sources do not explain this control.'}), event({}, 'stop')])
                chat = Chat(rounds)
                channel = Channel()
                reply = DiscordReply(channel)
                await reply.start()
                history = [{'role': 'system', 'content': 'Help'}, {'role': 'user', 'content': 'Close tips?'}]
                await stream_answer(SimpleNamespace(chat=chat), history, reply, HelpTools(lambda: {}, []), lambda: False)
                self.assertEqual(channel.text(), 'The available sources do not explain this control.')
                self.assertEqual(chat.requests[-1]['tool_choice'], 'none')
                self.assertNotIn(narration, json.dumps(chat.requests[-1]['messages']))
                self.assertNotIn(narration, json.dumps(history))

    async def test_tool_round_limit_and_empty_answer(self):
        rounds = [[event({'tool_calls': [call(0, 'search_commands', '{"query":""}', 'abcdef123')]}),
                   event({}, 'tool_calls')] for _ in range(4)]
        rounds.append([event({}, 'stop')])
        chat = Chat(rounds)
        reply = DiscordReply(Channel())
        await reply.start()
        await stream_answer(SimpleNamespace(chat=chat), [{'role': 'system', 'content': 'Help'}],
                            reply, HelpTools(lambda: {}, []), lambda: False)
        self.assertEqual(chat.requests[-1]['tool_choice'], 'none')
        self.assertTrue(reply.full_text)

    async def test_stop_and_failure_preserve_visible_text(self):
        for stop in (True, False):
            channel = Channel()
            reply = DiscordReply(channel)
            await reply.start()
            history = [{'role': 'system', 'content': 'Help'}]
            chat = Chat([[event({}, 'stop')], [event({'content': 'answer ' * 400})]])
            if stop:
                await stream_answer(SimpleNamespace(chat=chat), history, reply, HelpTools(lambda: {}, []),
                                    lambda: bool(reply.full_text))
                self.assertTrue(reply.full_text.endswith('-- (AI was Stopped by command)'))
            else:
                chat.stream_async = AsyncMock(side_effect=RuntimeError('upstream failed'))
                await reply.append('Already streamed text')
                with self.assertRaises(RuntimeError):
                    await stream_answer(SimpleNamespace(chat=chat), history, reply, HelpTools(lambda: {}, []), lambda: False)
            self.assertEqual(history[-1]['content'], channel.text())


if __name__ == '__main__':
    unittest.main()
