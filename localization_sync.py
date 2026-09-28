"""Export, upload, and release approved Crowdin catalogs without starting the bot."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from localization import ROOT, LANGUAGES, export_custom, fields, write_json


def read_strings(path):
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict) or any(not isinstance(value, str) for value in result.values()):
        raise ValueError(f"Expected a string catalog: {path}")
    return result


def validate(source, translated, custom=False):
    result = {}
    for key, value in translated.items():
        if key not in source or not value:
            continue
        if custom:
            if '.name.' in key and (len(value) > 100 or any(c.isspace() for c in value) or value.startswith('!')):
                raise ValueError(f"Invalid custom command alias: {key}")
            if '.info.' in key and len(value) > 2000:
                raise ValueError(f"Custom reply exceeds Discord's 2000-character limit: {key}")
        else:
            if fields(value) != fields(source[key]):
                raise ValueError(f"Translation placeholders differ from English: {key}")
            if key.startswith('commands.') and len(value) > 100:
                raise ValueError(f"Slash description exceeds 100 characters: {key}")
            if key == source[key] and '.' not in key:
                if not 1 <= len(value) <= 32 or value != value.lower() or any(not (c.isalnum() or c in '-_') for c in value):
                    raise ValueError(f"Invalid slash command name: {key}")
        result[key] = value
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('export', 'upload', 'download'))
    parser.add_argument('--config', type=Path, default=ROOT / 'config.json', help='Bot config containing custom commands')
    parser.add_argument('--language', choices=[code for code in LANGUAGES if code != 'en-US'], default='ja')
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    custom = export_custom(config, ROOT)
    if args.action == 'export':
        print(f"Exported {len(custom)} custom-command strings.")
        return
    if args.action == 'upload':
        subprocess.run(['crowdin', 'upload', 'sources', '--config', str(ROOT / 'crowdin.yml')], cwd=ROOT, check=True)
        return
    # Stage downloads so an interrupted download cannot overwrite live catalogs.
    with tempfile.TemporaryDirectory(prefix='ou-bot-translations-') as directory:
        stage = Path(directory)
        source = read_strings(ROOT / 'translations/en.json')
        write_json(stage / 'translations/en.json', source)
        write_json(stage / 'translations/custom/en.json', custom)
        subprocess.run([
            'crowdin', 'download', '--config', str(ROOT / 'crowdin.yml'),
            '--base-path', str(stage), '--language', args.language,
            '--export-only-approved', '--skip-untranslated-strings',
        ], cwd=ROOT, check=True)
        ui = validate(source, read_strings(stage / f'translations/{args.language}/en.json'))
        commands = validate(custom, read_strings(stage / f'translations/custom/{args.language}/en.json'), custom=True)
        write_json(ROOT / f'translations/{args.language}.json', ui)
        write_json(ROOT / f'translations/custom/{args.language}.json', commands)
    print('Released approved translations. Restart the bot or use moderator !sync to reload.')


if __name__ == '__main__':
    main()
