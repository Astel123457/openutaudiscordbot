import discord
from discord.ext import commands
import os
import json
token = "ODg5NzExMTgzMzEyMDgwOTQ3.GzMPBY.xJ2f4kSQ-eRLy5r_cRkqyyTfth8SIy38pW9cEE"

intents = discord.Intents.default()
intents.message_content = True
if not os.path.exists("config.json"):
    with open("config.json", "w") as f:
        json.dump({"":""}, f)
with open("config.json", "r") as f:
    config = json.load(f)

client = commands.Bot(command_prefix='!', intents=intents, status=discord.Status.online)
@client.event
async def on_ready():
    print("Client has started")

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if message.content.startswith('!'):
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
    
    conf = config.get(command, None)  # example is the name of the command that you are making
    if conf is None:
        config[command] = {}
        conf = config.get(command, None)
    conf["has_image"] = True
    image_path = await ctx.message.attachments[0].save(ctx.message.attachments[0].filename)  # this is the image that is being sent
    conf["image"] = ctx.message.attachments[0].filename

    # Write the updated config to config.json
    with open("config.json", "w") as f:
        json.dump(config, f)

    await ctx.send(f"The image for the command `{command}` has been set successfully!")

async def example(ctx: discord.Interaction): #this command is not exposed to the user
    conf = config.get("example", None) # example is the name of the command that you are making
    if conf is not None:
        has_image = conf.get("has_image", None) # this is only if the command has a file that goes with it
        if has_image is None:
            conf["has_image"] = False
    else: has_image = False
    if has_image:
        ctx.send("whatever needs to be sent here, such as links, info on what to do ext, could use config to store this info, can be blank if an image is being sent", file=discord.File(conf["image"])) # this is if the command has an image/gif/whatever
    else:
        ctx.send("whatever needs to be sent here, such as links, info on what to do ext, could use config to store this info") # this is if the command does not have an image/gif/whatever
@client.command()
async def make_command(ctx: discord.Interaction, command: str, *, info: str = None):
    print("Making command")
    print(config)
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


client.run(token)

