import discord
from discord.ext import commands
import os
import json
import secretsd as sec
from difflib import get_close_matches
token = sec.discord_token

intents = discord.Intents().default()
intents.message_content = True
if not os.path.exists("config.json"):
    with open("config.json", "w") as f:
        json.dump({"moderators":[493626802644713473]}, f)
with open("config.json", "r") as f:
    config = json.load(f)

command_list = [cmd for cmd in config.keys() if cmd not in ["make_command", "set_info", "set_image", "moderators"]]
command_list.sort()
print(command_list)

client = commands.Bot(command_prefix='!', intents=intents, status=discord.Status.online, activity=discord.Activity(type=discord.ActivityType.custom, name="Use !help or ping me!"))
client.remove_command("help")

@client.event
async def on_ready():
    print("Client has started")

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if message.content.startswith('!') and not message.content.startswith('!moderators'):
        command_name = message.content[1:].split()[0]  # Extract command name
        conf = config.get(command_name, None)
        print(conf)
        if conf is not None:  # Continue processing if the command exists
            info = conf.get("info", None)  # Info can now be None
            has_image = conf.get("has_image", False)
            if has_image:
                image_path = conf.get("image", None)
                if image_path and os.path.exists(image_path):
                    if info:
                        await message.channel.send(info, file=discord.File(image_path))
                    else:
                        await message.channel.send(file=discord.File(image_path))
                else:
                    if info:
                        await message.channel.send(info)
            elif info:
                await message.channel.send(info)
    if client.user.mentioned_in(message):
        embed = discord.Embed(title="Hello!", description="This Bot is used to help the users of the Openutau discord server.\nIf you would like some help, check out one of the links below.", color=0x00ff00)
        embed.add_field(name="Getting Started", value="https://github.com/stakira/OpenUtau/wiki/Getting-Started", inline=False)
        embed.add_field(name="Frequently Asked Questions", value="https://github.com/stakira/OpenUtau/wiki/FAQ", inline=False)
        embed.add_field(name="Have issues? Send them here! (Or in #help-en)", value="https://github.com/stakira/OpenUtau/issues", inline=False)
        await message.channel.send(embed=embed)
    await client.process_commands(message)

@client.command()
async def set_image(ctx: discord.Interaction, command: str):
    if ctx.author.id not in config["moderators"]:
        await ctx.send("You do not have permission to use this command.")
        return
    conf = config.get(command, None)  # example is the name of the command that you are making
    if conf is None:
        config[command] = {}
        conf = config.get(command, None)
    conf["has_image"] = True
    if len(ctx.message.attachments) == 0:
        await ctx.send("You must provide an image. (Links are not supported at this time)")
        return
    image_path = await ctx.message.attachments[0].save(ctx.message.attachments[0].filename)  # this is the image that is being sent
    conf["image"] = ctx.message.attachments[0].filename

    # Write the updated config to config.json
    with open("config.json", "w") as f:
        json.dump(config, f, indent=4)

    await ctx.send(f"The image for the command `{command}` has been set successfully!")

@client.command()
async def set_info(ctx: discord.Interaction, command: str, *, info: str):
    if ctx.author.id not in config["moderators"]:
        await ctx.send("You do not have permission to use this command.")
        return
    
    conf = config.get(command, None)

    if conf is None:
        await ctx.send(f"The command `{command}` does not exist.")
        return
    
    conf["info"] = info
    
    with open("config.json", "w") as f:
        json.dump(config, f, indent=4)

    await ctx.send(f"The info for the command `{command}` has been set successfully!")

@client.command()
async def make_command(ctx: discord.Interaction, command: str, *, info: str = None):
    if ctx.author.id not in config["moderators"]:
        await ctx.send("You do not have permission to use this command.")
        return
    
    if command in config:
        await ctx.send(f"The command `{command}` already exists.")
        return

    has_image = len(ctx.message.attachments) > 0
    if not has_image and not info:
        await ctx.send("You must provide either an info message, an image, or both.")
        return

    config[command] = {"info": info, "has_image": has_image}

    if has_image:
        image_path = await ctx.message.attachments[0].save(command + ".png")
        config[command]["image"] = command + ".png"  

    with open("config.json", "w") as f:
        json.dump(config, f, indent=4)
    await ctx.send(f"The command `{command}` has been created successfully!")
    
@client.command()
async def remove_command(ctx: discord.Interaction, command: str = None):
    if ctx.author.id not in config["moderators"]:
        await ctx.send("You do not have permission to use this command.")
        return
    if command is None:
        await ctx.send("You must provide a command to remove.")
        return
    if command not in config:
        await ctx.send(f"The command `{command}` does not exist.")
        return

    removed_command = config.pop(command)

    if removed_command.get("has_image") and "image" in removed_command:
        image_path = removed_command["image"]
        if os.path.exists(image_path):
            os.remove(image_path)

    with open("config.json", "w") as f:
        json.dump(config, f, indent=4)

    await ctx.send(f"The command `{command}` has been removed successfully!")

@client.command()
async def add_bot_moderator(ctx: discord.Interaction, user: discord.User):
    if ctx.author.id not in config["moderators"]:
        await ctx.send("You do not have permission to use this command.")
        return

    if user.id in config["moderators"]:
        await ctx.send(f"{user.name} is already a moderator.")
        return

    config["moderators"].append(user.id)
    with open("config.json", "w") as f:
        json.dump(config, f, indent=4)

    await ctx.send(f"{user.name} has been added as a moderator.")

@client.command()
async def moderators(ctx: discord.Interaction):
    if ctx.author.id not in config["moderators"]:
        await ctx.send("You do not have permission to use this command.")
        return

    moderator_list = [user_id for user_id in config["moderators"]]
    if not moderator_list:
        await ctx.send("No moderators have been added yet.")
    else:
        mods = []
        for user_id in moderator_list:
            try:
                mods.append(f"{await client.fetch_user(user_id)}: (ID: {user_id})")
            except discord.NotFound:
                mods.append(f"Unknown User: (ID: {user_id})")
        moderators_str = "\n".join(mods)
        await ctx.send(f"Here are the current moderators:\n\n{moderators_str}")

@client.command()
async def rename_command(ctx: discord.Interaction, old_name: str, new_name: str):
    if ctx.author.id not in config["moderators"]:
        await ctx.send("You do not have permission to use this command.")
        return

    if old_name not in config:
        await ctx.send(f"The command `{old_name}` does not exist.")
        return

    if new_name in config:
        await ctx.send(f"The command `{new_name}` already exists.")
        return

    config[new_name] = config.pop(old_name)

    with open("config.json", "w") as f:
        json.dump(config, f, indent=4)

    await ctx.send(f"The command `{old_name}` has been renamed to `{new_name}` successfully!")

def split_list(input_list, page_size):
    pages = [input_list[i:i + page_size] for i in range(0, len(input_list), page_size)]
    
    num_pages = len(pages)
    
    return pages, num_pages

def autocorrect_command(command_name):
    global command_list
    command_name = command_name.lower()
    
    # First, prioritize commands that contain the input as a substring
    substring_matches = [cmd for cmd in command_list if command_name in cmd.lower()]
    
    # Then, find other close matches using get_close_matches
    close_matches = get_close_matches(command_name, command_list, n=10, cutoff=0.1)
    
    # Combine the results, ensuring no duplicates and preserving order
    combined_matches = list(dict.fromkeys(substring_matches + close_matches))
    
    return combined_matches

@client.command()
async def list_commands(ctx: discord.Interaction, page: int = 1, filter: str = None):
    global command_list
    page = page - 1
    pages, num_pages = split_list(command_list, 10)
    if not command_list:
        await ctx.send("No commands have been created yet.")
    else:
        if page >= num_pages or page < 0:
            await ctx.send(f"Invalid page number. There are only {num_pages} pages.")
            return
        if filter is not None:
            output = autocorrect_command(filter)
            commands_str = "\n".join(output)
            await ctx.send(f"Here are the closest commands to what you entered:\n\n{commands_str}")
            return
        commands_str = "\n".join(pages[page])
        print(page)
        await ctx.send(f"Here are the available commands:\n\n{commands_str}\n\nPage {page + 1}/{num_pages}. Use `!list_commands <page number>` to change the page.")

client.run(token)