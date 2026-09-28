"""Discord slash-command adapter for the reviewed localization catalogs."""
from discord import app_commands
from localization import catalog, locale_code


def localized(key):
    # Discord requires actual English as the default, not a translation key.
    return app_commands.locale_str(catalog.text(key), key=key)


class MyTranslator(app_commands.Translator):
    async def translate(self, string, locale, context):
        key = string.extras.get("key", str(string))
        translated = catalog.ui.get(locale_code(locale), {}).get(key)
        if not translated:
            return None
        location = context.location.name
        if location.endswith("name"):
            if not 1 <= len(translated) <= 32 or any(not (c.isalnum() or c in "-_") for c in translated) or translated != translated.lower():
                return None
        if location.endswith("description") and not 1 <= len(translated) <= 100:
            return None
        return translated
