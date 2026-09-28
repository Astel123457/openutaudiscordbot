"""Reviewed file-based localization; no runtime machine translation or network calls."""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from string import Formatter

ROOT = Path(__file__).resolve().parent
LANGUAGES = {"en-US": "English", "ja": "日本語"}
RESERVED_CONFIG = {"moderators", "stickynotes", "sticky_messages", "channel_command_cooldowns", "channel_languages"}


def locale_code(locale):
    value = getattr(locale, "value", locale)
    if value in ("en", "en-GB", "en-US", None):
        return "en-US"
    return value if value in LANGUAGES else "en-US"


def normalized_name(name):
    return name.casefold().replace("-", "").replace("_", "")


def custom_commands(config):
    return {name: entry for name, entry in config.items()
            if name not in RESERVED_CONFIG and isinstance(entry, dict)
            and any(field in entry for field in ("info", "image", "has_image"))}


def custom_key(name, field, source):
    # Content revisions prevent serving an old approved answer after an edit.
    revision = hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]
    return f"custom.{name}.{field}.{revision}"


def custom_sources(config):
    result = {}
    for name, entry in sorted(custom_commands(config).items()):
        result[custom_key(name, "name", name)] = name
        if isinstance(entry.get("info"), str) and entry["info"]:
            result[custom_key(name, "info", entry["info"])] = entry["info"]
    return result


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def export_custom(config, root=ROOT):
    path = Path(root) / "translations/custom/en.json"
    sources = custom_sources(config)
    if not path.exists() or json.loads(path.read_text(encoding="utf-8")) != sources:
        write_json(path, sources)
    return sources


def fields(text):
    return {name for _, name, _, _ in Formatter().parse(text) if name is not None}


class Catalog:
    def __init__(self, root=ROOT):
        self.root = Path(root)
        self.reload()

    def _read(self, path):
        try:
            values = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(values, dict) or any(not isinstance(v, str) for v in values.values()):
                raise ValueError("Catalog must be an object containing strings")
            return values
        except FileNotFoundError:
            return {}
        except (ValueError, OSError) as exc:
            logging.warning("Cannot load translation catalog %s: %s", path, exc)
            return {}

    def reload(self):
        self.english = self._read(self.root / "translations/en.json")
        self.ui = {code: self._read(self.root / f"translations/{code}.json")
                   for code in LANGUAGES if code != "en-US"}
        self.custom = {code: self._read(self.root / f"translations/custom/{code}.json")
                       for code in LANGUAGES if code != "en-US"}

    def text(self, key, locale=None, **values):
        source = self.english.get(key, key)
        translated = self.ui.get(locale_code(locale), {}).get(key) or source
        if values:
            try:
                if fields(translated) != fields(source):
                    translated = source
                return translated.format(**values)
            except (ValueError, KeyError, IndexError, AttributeError):
                return source.format(**values)
        return translated

    def custom_text(self, name, field, source, locale=None):
        if not source:
            return source
        translated = self.custom.get(locale_code(locale), {}).get(custom_key(name, field, source))
        if not translated:
            return source
        if field == "name" and (len(translated) > 100 or any(c.isspace() for c in translated) or translated.startswith("!")):
            return source
        return translated

    def aliases(self, config, locale=None, reserved=()):
        commands = custom_commands(config)
        aliases = {}
        blocked = {normalized_name(name) for name in set(commands) | set(reserved) | RESERVED_CONFIG}
        for name in commands:
            alias = self.custom_text(name, "name", name, locale)
            if alias != name and normalized_name(alias) not in blocked:
                aliases.setdefault(normalized_name(alias), []).append((alias, name))
        return {entries[0][0]: entries[0][1] for entries in aliases.values() if len(entries) == 1}


catalog = Catalog()
