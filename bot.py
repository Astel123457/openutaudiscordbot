import discord
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
    print(config)

client = discord.Client(intents=intents, status=discord.Status.online)
@client.event
async def on_ready():
    print("Client has started")

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    
    if client.user.mentioned_in(message):
        embed = discord.Embed(title="Hello!", description="This Bot is used to help the users of the Openutau discord server.\nIf you would like some help, check out one of the links below.", color=0x00ff00)
        embed.add_field(name="Getting Started", value="https://github.com/stakira/OpenUtau/wiki/Getting-Started", inline=False)
        embed.add_field(name="Frequently Asked Questions", value="https://github.com/stakira/OpenUtau/wiki/FAQ", inline=False)
        embed.add_field(name="Have issues? Send them here! (Or in #help-en)", value="https://github.com/stakira/OpenUtau/issues", inline=False)
        await message.channel.send(embed=embed)

@client.command()
async def set_image(ctx: discord.Interaction, command: str):
    print("Setting image")
    conf = config.get(command, None) # example is the name of the command that you are making
    conf["has_image"] = True
    image_path = await ctx.attachments[0].save(ctx.attachements[0].filename) # this is the image that is being sent
    conf["image"] = ctx.attachements[0].filename

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
async def mrbeast(ctx):
    print("MRBEAST!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    conf = config.get("mrbeast", None) # example is the name of the command that you are making
    ctx.send(file=discord.File(conf["image"])) # this is if the command has an image/gif/whatever
    
client.run(token)
