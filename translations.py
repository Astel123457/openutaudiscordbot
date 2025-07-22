from __future__ import annotations

import discord
from discord import app_commands
# this apperenlty doesn't work but we'll leave it for now, just in case things start working again

class MyTranslator(app_commands.Translator):
    async def translate(
        self,
        string: app_commands.locale_str,
        locale: discord.Locale,
        context: app_commands.TranslationContext,
    ) -> str | None:
        # For this example, we can translate a few words in Japanese...
        print(f"Translating '{string}' for locale '{locale}'")
        message = str(string)
        if locale is discord.Locale.japanese:
            if message == 'Make Sticky Note':
                return '付箋を作成する'
            elif message == 'Goodbye!':
                return 'さようなら！'

        # Otherwise we don't handle it
        return None