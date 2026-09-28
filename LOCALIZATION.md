# Reviewed translations

Crowdin project: [OpenUtauDiscordBot](https://crowdin.com/project/openutaudiscordbot)
(project ID `934405`, configured in `crowdin.yml`).

English is the source language; Japanese (`ja`, not `jp`) is the first target.
There is no runtime machine translation. Missing translations use English.
The old Japanese catalog is preserved in `translations/drafts/ja.json` for human
review; the bot never loads drafts. `translations/ja.json` starts empty on purpose.

## Create the Crowdin project

1. Select English as the source language and Japanese as the target language.
2. Leave automatic pretranslation / machine translation off. Have a proofreader
   approve translations before release. If the project offers an export setting,
   select approved translations only; the download script also enforces this.
3. Install the [Crowdin CLI](https://crowdin.github.io/crowdin-cli/installation/).
   Set `CROWDIN_PERSONAL_TOKEN` in the deployment environment. The project ID is
   already configured in `crowdin.yml`.
   Do not put the token in the repository or `crowdin.yml`.

From this directory, on the host with the bot's current `config.json`:

```sh
python localization_sync.py export
python localization_sync.py upload
```

Use `--config /path/to/config.json` if the live configuration lives elsewhere.
The upload command always re-exports the current custom commands first. Only
`translations/en.json` and `translations/custom/en.json` are uploaded. Moderator
IDs, channel settings, sticky notes, conversation history, images, and tokens are
not included. Custom command names and answer text will be visible to project
translators, according to the project's visibility settings.

The bot refreshes the local custom source file whenever commands are created,
edited, renamed, deleted, or imported. Run the upload command after these changes,
or schedule that command on the bot host to automate source synchronization.
This only uploads source text; it does not translate or publish answers.

Optionally import `translations/drafts/ja.json` as unapproved Japanese translations
for the `translations/en.json` source file in Crowdin. Review them before approval;
they are existing drafts, not a complete Japanese translation.

## Review and release

Translate and approve strings in Crowdin, then run:

```sh
python localization_sync.py download --language ja
```

Downloads request both `--export-only-approved` and
`--skip-untranslated-strings`. Files are staged and validated before replacing
released catalogs. Restart the bot, or run the moderator-only `!sync` to reload
catalogs and update global Discord slash-command localizations. Discord can take
time to display updated global commands.

The [CLI export flags](https://crowdin.github.io/crowdin-cli/commands/crowdin-download/)
and [environment credentials](https://crowdin.github.io/crowdin-cli/configuration/)
are documented by Crowdin. Slash commands use real English defaults plus catalog
keys in [`locale_str` metadata](https://discordpy.readthedocs.io/en/stable/interactions/api.html#discord.app_commands.locale_str).

## Bot behavior

- Slash-command names/descriptions and localized interaction replies/modals follow
  the user's Discord language. English remains the default.
- A bot moderator uses `/channel-language` to choose English or Japanese for
  custom `!command` replies in a channel. Prefix messages have no user locale.
- Approved custom command names work as aliases; English command names keep
  working. Conflicting aliases are ignored. Images stay unchanged.
- Custom reply keys include a fingerprint of the English text. Editing an answer
  immediately stops using its old translation. Renamed/deleted commands cannot
  accidentally reuse the previous command's translated answer.
- English and Japanese custom catalogs are deployment data under
  `translations/custom/` and are ignored by Git. Upload/download on the deployment
  host, or transfer its catalogs there deliberately.
- AI-generated answers and user-authored sticky-note content are not translated
  through Crowdin.

## Adding another Discord language later

Add its exact Discord locale code to `LANGUAGES` in `localization.py`, enable its
Crowdin target language, and add a mapping from that Crowdin language ID to the
Discord locale code under **both** `languages_mapping.locale` entries in
`crowdin.yml`. For example, regional Discord locales must retain their regional
code instead of collapsing into a two-letter language. Upload sources, translate,
approve, and download with `--language CODE`. Restart and sync the bot.

Keep `{value0}`, `{language}`, and other format placeholders unchanged. Command
names must satisfy Discord's name restrictions and descriptions must fit 100
characters. Custom answer translations must fit Discord's 2,000-character message
limit. The release script rejects invalid entries rather than truncating them.
