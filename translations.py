from __future__ import annotations

import discord
from discord import app_commands
# this apperenlty doesn't work but we'll leave it for now, just in case things start working again

en = {
    "commands-stop": "stop", #these need to still follow discord's naming convention
    "commands.stop.description": "Stops the AI conversation in the current channel.",
    "commands-set-image": "set-image",
    "commands.set-image.description": "Sets an image for a custom command.",
    "commands-clear" : "clear",
    "commands.clear.description": "Clears the current channel's AI conversation.",

    
}
ja = {
    "commands.stop": "停止",
    "commands.stop.description": "現在のチャンネルでAIの会話を停止します。",
    "commands.set-image": "画像を設定",
    "commands.set-image.description": "カスタムコマンドの画像を設定します。",
    "commands.clear": "クリア",
    "commands.clear.description": "現在のチャンネルのAI会話をクリアします。",
}


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
            # If the locale is Japanese, return the Japanese translation, else return the English translation
            return ja.get(message, en.get(message, None))
        if locale is discord.Locale.american_english or locale is discord.Locale.british_english:
            # If the locale is English, return the English translation
            return en.get(message, None)
        # Otherwise we don't handle it
        return en.get(message, None)