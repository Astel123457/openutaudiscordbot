import discord
from discord.ext import commands
import os
import json
token = "ODg5NzExMTgzMzEyMDgwOTQ3.GzMPBY.xJ2f4kSQ-eRLy5r_cRkqyyTfth8SIy38pW9cEE"

intents = discord.Intents().default()
intents.message_content = True
if not os.path.exists("config.json"):
    with open("config.json", "w") as f:
        json.dump({"moderators":[493626802644713473]}, f)
with open("config.json", "r") as f:
    config = json.load(f)



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
        json.dump(config, f)

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
    # Write the updated config to config.json
    with open("config.json", "w") as f:
        json.dump(config, f)

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
        image_path = await ctx.message.attachments[0].save(ctx.message.attachments[0].filename)
        config[command]["image"] = ctx.message.attachments[0].filename

    with open("config.json", "w") as f:
        json.dump(config, f)
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
    
    # Remove the command from the config

    removed_command = config.pop(command)

    # Delete associated image file if it exists
    if removed_command.get("has_image") and "image" in removed_command:
        image_path = removed_command["image"]
        if os.path.exists(image_path):
            os.remove(image_path)

    # Write the updated config to config.json
    with open("config.json", "w") as f:
        json.dump(config, f)

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
        json.dump(config, f)

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
        for user_id in moderator_list:
            print(await client.fetch_user(user_id))
        moderators_str = "\n".join([f"{await client.fetch_user(user_id).name} (ID: {user_id})" if await client.fetch_user(user_id) else f"Unknown User (ID: {user_id})" for user_id in moderator_list])
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

    # Write the updated config to config.json
    with open("config.json", "w") as f:
        json.dump(config, f)

    await ctx.send(f"The command `{old_name}` has been renamed to `{new_name}` successfully!")

@client.command()
async def list_commands(ctx: discord.Interaction):
    command_list = [cmd for cmd in config.keys() if cmd not in ["make_command", "set_info", "set_image", "moderators"]]
    if not command_list:
        await ctx.send("No commands have been created yet.")
    else:
        commands_str = "\n".join(command_list)
        await ctx.send(f"Here are the available commands:\n\n{commands_str}")

client.run(token)