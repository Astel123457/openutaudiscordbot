from __future__ import annotations

import discord
from discord import app_commands
# this apperenlty doesn't work but we'll leave it for now, just in case things start working again

en = {
    "commands.stop.description": "Stops the AI conversation in the current channel.",
    "commands.set-image.description": "Sets an image for a custom command.",
    "commands.clear.description": "Clears the current channel's AI conversation.",
    "commands.end-finetuning.description": "Ends the current finetuning session.",
    "commands.start-finetuning.description": "Starts a finetuning session for the AI.",
    "commands.edit.description": "Edits the last message the AI sent in the current channel.",
    "commands.edit.new_content": "The new content to replace the last AI message with.",
    "commands.set-info.description": "Sets the informational text for a custom command.",
    "commands.set-info.info": "Informational text for the command.",
    "commands.make-command.description": "Creates a new custom command.",
    "commands.make-command.info": "Optional informational text for the command (if not provided, an image must be attached)",
    "commands.make-command.command": "The name of the command to create",
    "commands.make-command.attachment": "Optional image to attach to the command (if not provided, informational text must be provided)",
    "commands.remove-command.description": "Removes an existing custom command.",
    "commands.remove-command.command": "The name of the command to remove",
}
ja = {
    "commands.stop.description": "現在のチャンネルでAIの会話を停止します。",
    "commands.set-image.description": "カスタムコマンドの画像を設定します。",
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
        
        message = str(string)
        if locale is discord.Locale.japanese:
            # If the locale is Japanese, return the Japanese translation, else return the English translation
            return ja.get(message, en.get(message, None))
        if locale is discord.Locale.american_english or locale is discord.Locale.british_english:
            # If the locale is English, return the English translation
            return en.get(message, None)
        # Otherwise we don't handle it
        print(f"'{string}' was missing a translation")
        return en.get(message, None)