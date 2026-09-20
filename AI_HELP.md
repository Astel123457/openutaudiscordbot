AI replies still use the existing moderator-only `=` prefix and Mistral model.
Restart the bot after updating `bot.py` and adding `ai_support.py`.

The AI can now call three read-only tools:

- `search_commands`: searches current custom command names and saved answer text in `config.json`. Results include image availability, but exclude local image paths and bot settings. An empty query lists commands; results are paginated.
- `search_wiki`: searches OpenUtau GitHub wiki page titles, or lists pages with an empty query.
- `read_wiki_page`: retrieves a page's Markdown, URL, and continuation offset for long pages.

Wiki responses are cached for five minutes. Requests time out after 15 seconds;
lookup errors are returned to the model. Four tool rounds are allowed before a
final answer without tools. Streamed function-call fragments are assembled before
execution, and results are returned with the corresponding `tool_call_id`, following
[Mistral's function-calling documentation](https://docs.mistral.ai/studio/conversations/function-calling).

Discord reply buffers are finalized before starting the next message. This fixes
text lost between the last throttled preview edit and a message rollover. Oversized
chunks and stop notices use the same splitting logic. Requests in the same channel
are serialized to keep conversation history and stop flags consistent.

Run regression tests with installed project dependencies:

```sh
python -m unittest discover -s tests -v
```

The tests use mocked Discord messages and HTTP streams decoded by the actual Mistral
SDK. They do not need credentials or send Discord messages. A live end-to-end check
can use `=Find the saved command about phonemizers and check the OpenUtau wiki.`
