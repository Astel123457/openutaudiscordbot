from discord import app_commands, Locale


class BotTranslator(app_commands.Translator):
    
    async def translate(
        self, 
        string: app_commands.locale_str, locale: Locale, context: app_commands.TranslationContext ):
        print(string, locale, context)  # Debugging output to check the parameters
        if context.location == "make-command":  # check command name
            if locale is Locale.japanese:  # check locale
                print("translated")
                return "コマンドを作成する"  # return translated string
        return None