import discord
from discord.ext import commands
import asyncio
from difflib import get_close_matches
import os
import json
from mistralai import Mistral
import secretsd as sec
import time

# --- Configuration and Initialization ---
token = sec.discord_token
mistral_api_key = sec.mistral_api_key

# Ensure intents are correctly set for message content and reactions
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True # Crucial for reaction-based pagination
mistral_client = Mistral(api_key=mistral_api_key)

# Load or create config.json
if not os.path.exists("config.json"):
    with open("config.json", "w") as f:
        json.dump({"moderators":[493626802644713473]}, f, indent=4) # Added indent for readability
with open("config.json", "r") as f:
    config = json.load(f)

command_list = []
channel_based_message_history = {}

def update_command_list():
    """Updates the global command_list from the current config."""
    global command_list
    global config

    with open("config.json", "r") as f:
        config.clear()
        config.update(json.load(f))

    command_list.clear()
    internal_commands = ["make_command", "set_info", "set_image", "moderators",
                         "remove_command", "add_bot_moderator", "rename_command",
                         "list_commands", "bot_config", ]
    command_list.extend([cmd for cmd in config.keys() if cmd not in internal_commands])
    command_list.sort()

update_command_list()

client = commands.Bot(command_prefix='!', intents=intents, status=discord.Status.online,
                      activity=discord.Activity(type=discord.ActivityType.custom, name="Use !help or ping me!"))
client.remove_command("help")

# --- Bot Events ---
@client.event
async def on_ready():
    """Called when the bot is ready and connected to Discord."""
    print(f"Logged in as {client.user.name}")
    print(f"Bot ID: {client.user.id}")
    print("Client has started")

async def get_message_history(channel, limit=10):
    messages = []
    async for msg in channel.history(limit=limit):
        if msg.type == discord.MessageType.default and not msg.author.bot and msg.author != client.user:
            formatted_message = f"{msg.author.display_name}: {msg.content}"
            messages.append(formatted_message)
    return "\n".join(reversed(messages))

@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return
    
    starts_with_prefix = message.content.startswith('=')
    last_sent = time.time()
    if starts_with_prefix:
        if not message.author.id in config.get("moderators", []):
            await message.channel.send("Only trusted users are allowed to use the AI chat function for the moment.")
            return
        prompt = message.content[1:].strip()
        #Get the channel ID to use as a key for message history
        channel_id = str(message.channel.id)
        if channel_id not in channel_based_message_history:
            channel_based_message_history[channel_id] = []
        # Append the new message to the channel's history
        mess = {"role": "user", "content": [ {"type": "text", "text": prompt}]}
        if message.attachments:
            for attachment in message.attachments:
                mess["content"].append({"type": "image_url", "image_url": attachment.url})
        channel_based_message_history[channel_id].append(mess)
        full_output = "" # we use this to store the full output from the model, then we'll append this to the channel history
        current_message_content = "" #we will erase the content in this if the output is too long
        async with message.channel.typing():
            main_message = await message.channel.send("...")
            response = await mistral_client.chat.stream_async(
            messages=channel_based_message_history[channel_id],\
            #TODO: use a custom fine-tuned model specific to OpenUtau, once trained
            model="pixtral-12b-latest",
            temperature=0.7,
            safe_prompt=True,
            max_tokens=1000,
            top_p=0.95,
            )
            async for chunk in response:
                print(chunk)
                if chunk.data.choices[0].delta.content:
                    full_output += chunk.data.choices[0].delta.content
                    if len(full_output) + 3 > 2000:
                        current_message_content = chunk.data.choices[0].delta.content
                        main_message = await message.channel.send("...")
                    else:
                        current_message_content += chunk.data.choices[0].delta.content
                if chunk.data.choices[0].finish_reason != None:
                    await main_message.edit(content=current_message_content)
                    # Append the full output to the channel's history
                    channel_based_message_history[channel_id].append({"role": "assistant", "content": [{"type": "text", "text": full_output}]})
                    break
                time_delta = last_sent - time.time()
                print(f"Time since last message sent/edited: {time_delta:.2f} seconds")
                if time_delta < .6:
                    continue #restart the loop if it's not been about .6 seconds since the last message was sent/edited, to avoid rate limiting
                else:
                    last_sent = time.time()
                    await main_message.edit(content=current_message_content+"...")
                    

    if message.content.startswith(client.command_prefix) and not message.content.startswith(f'{client.command_prefix}moderators'):
        command_name = message.content[len(client.command_prefix):].split()[0]
        conf = config.get(command_name, None)

        if conf is not None: # If the command exists in config
            info = conf.get("info", None)
            has_image = conf.get("has_image", False)

            if has_image:
                image_path = conf.get("image", None)
                if image_path and os.path.exists(image_path):
                    try:
                        # Send info and image if both exist, otherwise just image
                        if info:
                            await message.channel.send(info, file=discord.File(image_path))
                        else:
                            await message.channel.send(file=discord.File(image_path))
                        print(f"Sent image for command {command_name} from {image_path}")
                    except Exception as e:
                        print(f"Error sending image for command {command_name}: {e}")
                else:
                    print(f"Image path not found or invalid for command {command_name}: {image_path}")
                    if info:
                        await message.channel.send(info)
            elif info:
                await message.channel.send(info)
            return 

    # Handle bot mentions
    if client.user.mentioned_in(message):
        embed = discord.Embed(title="Hello!", description="This Bot is used to help the users of the Openutau discord server.\nIf you would like some help, check out one of the links below.", color=0x00ff00)
        embed.add_field(name="Getting Started", value="https://github.com/stakira/OpenUtau/wiki/Getting-Started", inline=False)
        embed.add_field(name="Frequently Asked Questions", value="https://github.com/stakira/OpenUtau/wiki/FAQ", inline=False)
        embed.add_field(name="Have issues? Send them here! (Or in #help-en)", value="https://github.com/stakira/OpenUtau/issues", inline=False)
        await message.channel.send(embed=embed)
    await client.process_commands(message)

# --- Utility Functions ---
def split_list(input_list, page_size):
    """Divides a list into pages of a given size."""
    pages = [input_list[i:i + page_size] for i in range(0, len(input_list), page_size)]
    num_pages = len(pages)
    return pages, num_pages

def autocorrect_command(command_name):
    """
    Suggests commands based on substring matches and close matches.
    Uses the global command_list.
    """
    global command_list
    command_name = command_name.lower()

    substring_matches = [cmd for cmd in command_list if command_name in cmd.lower()]
    close_matches = get_close_matches(command_name, command_list, n=10, cutoff=0.1)
    combined_matches = list(dict.fromkeys(substring_matches + close_matches))
    return combined_matches

async def send_temp_error(ctx: discord.Interaction, message_content: str, error_message_lifetime: int = 10):
        embed = discord.Embed(
            description=message_content,
            color=discord.Color.red()
        )
        embed.set_footer(text=f"This message will remove in {error_message_lifetime} seconds.")
        msg = await ctx.send(embed=embed)
        await asyncio.sleep(error_message_lifetime)
        try:
            await msg.delete()
        except discord.NotFound:
            pass

# --- Bot Commands ---
@client.command()
async def set_image(ctx: commands.Context, command: str): 
    """
    Sets an image for a custom command.
    Requires moderator permissions.
    Usage: !set_image <command_name> (attach image)
    """
    if ctx.author.id not in config["moderators"]:
        await ctx.send("You do not have permission to use this command.")
        return

    conf = config.get(command, None)
    if conf is None:
        # If command doesn't exist, create a basic entry for it
        config[command] = {}
        conf = config.get(command, None)

    conf["has_image"] = True
    if not ctx.message.attachments:
        await ctx.send("You must provide an image. (Links are not supported at this time)")
        return

    image_path = await ctx.message.attachments[0].save(command + ".png")  # this is the image that is being sent
    conf["image"] = command + ".png"  

    with open("config.json", "w") as f:
        json.dump(config, f, indent=4)

    update_command_list() 
    await ctx.send(f"The image for the command `{command}` has been set successfully!")

@client.command()
async def set_info(ctx: commands.Context, command: str, *, info: str):
    """
    Sets the informational text for a custom command.
    Requires moderator permissions.
    Usage: !set_info <command_name> <info_text>
    """
    if ctx.author.id not in config["moderators"]:
        await ctx.send("You do not have permission to use this command.")
        return

    conf = config.get(command, None)
    if conf is None:
        await ctx.send(f"The command `{command}` does not exist. Use `!make_command` to create it first.")
        return

    conf["info"] = info

    with open("config.json", "w") as f:
        json.dump(config, f, indent=4)

    update_command_list()
    await ctx.send(f"The info for the command `{command}` has been set successfully!")

@client.command()
async def make_command(ctx: commands.Context, command: str, *, info: str = None):
    """
    Creates a new custom command.
    Requires moderator permissions.
    Usage: !make_command <command_name> [info_text] (attach image)
    """
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
        image_filename = command + ".png"
        image_path = os.path.join("images", image_filename)
        os.makedirs(os.path.dirname(image_path), exist_ok=True)
        await ctx.message.attachments[0].save(image_path)
        config[command]["image"] = image_path

    with open("config.json", "w") as f:
        json.dump(config, f, indent=4)

    update_command_list()
    await ctx.send(f"The command `{command}` has been created successfully!")

@client.command()
async def remove_command(ctx: commands.Context, command: str = None): 
    """
    Removes an existing custom command.
    Requires moderator permissions.
    Usage: !remove_command <command_name>
    """
    if ctx.author.id not in config["moderators"]:
        await ctx.send("You do not have permission to use this command.")
        return
    if command is None:
        await ctx.send("You must provide a command to remove.")
        return
    if command not in config:
        await ctx.send(f"The command `{command}` does not exist.")
        return

    removed_command_data = config.pop(command)

    # If the command had an associated image, delete the file
    if removed_command_data.get("has_image") and "image" in removed_command_data:
        image_path = removed_command_data["image"]
        if os.path.exists(image_path):
            try:
                os.remove(image_path)
                print(f"Removed image file: {image_path}")
            except OSError as e:
                print(f"Error removing image file {image_path}: {e}")

    with open("config.json", "w") as f:
        json.dump(config, f, indent=4)

    update_command_list()
    await ctx.send(f"The command `{command}` has been removed successfully!")

@client.command()
async def add_bot_moderator(ctx: commands.Context, user: discord.User): 
    """
    Adds a user as a bot moderator.
    Requires existing moderator permissions.
    Usage: !add_bot_moderator <@user>
    """
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
async def moderators(ctx: commands.Context): 
    """
    Lists all current bot moderators.
    Requires moderator permissions.
    Usage: !moderators
    """
    if ctx.author.id not in config["moderators"]:
        await ctx.send("You do not have permission to use this command.")
        return

    moderator_ids = config["moderators"]
    if not moderator_ids:
        await ctx.send("No moderators have been added yet.")
    else:
        mods = []
        for user_id in moderator_ids:
            try:
                user = await client.fetch_user(user_id)
                mods.append(f"{user.name}#{user.discriminator} (ID: {user_id})")
            except discord.NotFound:
                mods.append(f"Unknown User (ID: {user_id})")
        moderators_str = "\n".join(mods)
        embed = discord.Embed(
            title="Current Bot Moderators",
            description=moderators_str,
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

@client.command()
async def rename_command(ctx: commands.Context, old_name: str, new_name: str): 
    """
    Renames an existing custom command.
    Requires moderator permissions.
    Usage: !rename_command <old_name> <new_name>
    """
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

    if config[new_name].get("has_image") and "image" in config[new_name]:
        old_image_path = config[new_name]["image"]
        old_image_filename = os.path.basename(old_image_path)
        old_image_ext = os.path.splitext(old_image_filename)[1]
        new_image_filename = new_name + old_image_ext
        new_image_path = os.path.join("images", new_image_filename)

        if os.path.exists(old_image_path):
            try:
                os.rename(old_image_path, new_image_path)
                config[new_name]["image"] = new_image_path
                print(f"Renamed image from {old_image_path} to {new_image_path}")
            except OSError as e:
                print(f"Error renaming image file {old_image_path} to {new_image_path}: {e}")
        else:
            print(f"Old image path not found for renaming: {old_image_path}")


    with open("config.json", "w") as f:
        json.dump(config, f, indent=4)

    update_command_list()
    await ctx.send(f"The command `{old_name}` has been renamed to `{new_name}` successfully!")

@client.command()
async def bot_config(ctx: discord.Interaction):
    error_message_lifetime = 30
    global config
    if ctx.author.id not in config["moderators"]:
        await send_temp_error(ctx, "You do not have permission to use this command.", 10)
        return

    # If the user uploads a file, load and save it as config.json
    if hasattr(ctx.message, "attachments") and ctx.message.attachments:
        attachment = ctx.message.attachments[0]
        if attachment.filename.endswith(".json"):
            file_bytes = await attachment.read()
            try:
                config = json.loads(file_bytes.decode("utf-8"))
                with open("config.json", "w") as f:
                    json.dump(config, f, indent=4)
                update_command_list()
                await ctx.send("The config file has been updated successfully.")
            except Exception as e:
                await send_temp_error(ctx, f"Failed to load config: {e}", error_message_lifetime)
        else:
            await send_temp_error(ctx, "Please upload a valid JSON file.", error_message_lifetime)
    else:
        # Otherwise, send the current config.json file
        if os.path.exists("config.json"):
            await ctx.send(file=discord.File("config.json"))
        else:
            await send_temp_error(ctx, "The config file does not exist.", error_message_lifetime)

@client.command(name='list_commands', aliases=['commands', 'helpme'])
async def list_commands(ctx: commands.Context, *, page_or_filter: str = None):
    """
    Lists all available commands, paginated, with interactive navigation.
    You can also search for a specific command.
    Usage: !list_commands [page_number|command_name]
    """
    update_command_list()

    COMMANDS_PER_PAGE = 10
    command_pages, num_pages = split_list(command_list, COMMANDS_PER_PAGE)
    current_page = 0

    if not command_list: # Case 1: No commands available
        embed = discord.Embed(
            title="No Commands Available",
            description="It seems there are no custom commands to display yet. Moderators can create them using `!make_command`.",
            color=discord.Color.orange()
        )
        embed.set_footer(text="This message will disappear in 60 seconds.")
        msg = await ctx.send(embed=embed)
        await asyncio.sleep(60)
        try:
            await msg.delete()
        except discord.NotFound:
            pass
        return

    # Handle filtering by command name (Case 2: Search query)
    if page_or_filter and not page_or_filter.isdigit():
        search_query = page_or_filter
        found_commands = autocorrect_command(search_query)
        if found_commands:
            embed = discord.Embed(
                title=f"Commands matching '{search_query}'",
                description="\n".join(found_commands),
                color=discord.Color.blue()
            )
            embed.set_footer(text="This search result will disappear in 60 seconds.")
            msg = await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                title="No Commands Found",
                description=f"No commands matching '{search_query}' were found. Try `!list_commands` to see all commands.",
                color=discord.Color.red()
            )
            embed.set_footer(text="This message will disappear in 60 seconds.")
            msg = await ctx.send(embed=embed)

        await asyncio.sleep(60)
        try:
            await msg.delete()
        except discord.NotFound:
            pass
        return

    # Handle direct page number input (Case 3: Invalid page number)
    if page_or_filter and page_or_filter.isdigit():
        try:
            requested_page = int(page_or_filter) - 1
            if not (0 <= requested_page < num_pages):
                embed = discord.Embed(
                    title="Invalid Page Number",
                    description=f"Page number must be between 1 and {num_pages}.",
                    color=discord.Color.red()
                )
                embed.set_footer(text="This message will disappear in 60 seconds.")
                msg = await ctx.send(embed=embed)
                await asyncio.sleep(60)
                try:
                    await msg.delete()
                except discord.NotFound:
                    pass
                return 
            current_page = requested_page 
        except ValueError:
            pass

    # --- Embed Creation and Initial Send (This part is for the interactive pagination) ---
    def create_commands_embed(page_index):
        if not command_pages or not (0 <= page_index < len(command_pages)):
            return discord.Embed(
                title="Error Displaying Commands",
                description="Could not find commands for this page.",
                color=discord.Color.red()
            )

        commands_on_page = command_pages[page_index]
        commands_str = "\n".join(commands_on_page)

        embed = discord.Embed(
            title="Available Commands",
            description=f"Here are the commands you can use:\n\n{commands_str}",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Page {page_index + 1}/{num_pages} | React to navigate. This message will expire in 60 seconds.")
        return embed

    message = await ctx.send(embed=create_commands_embed(current_page))

    # --- Add Reactions for Navigation ---
    if num_pages > 1:
        await message.add_reaction("◀️")
        await message.add_reaction("▶️")
        await message.add_reaction("❌")

    # --- Reaction Listener Loop ---
    def check(reaction, user):
        return (user == ctx.author and
                str(reaction.emoji) in ["◀️", "▶️", "❌"] and
                reaction.message.id == message.id)

    while True:
        try:
            reaction, user = await client.wait_for("reaction_add", timeout=60.0, check=check)

            try:
                await message.remove_reaction(reaction, user)
            except discord.HTTPException:
                print(f"Could not remove reaction: {reaction.emoji} by {user.name}. Check bot permissions.")

            if str(reaction.emoji) == "▶️":
                current_page = (current_page + 1) % num_pages
            elif str(reaction.emoji) == "◀️":
                current_page = (current_page - 1 + num_pages) % num_pages
            elif str(reaction.emoji) == "❌":
                await message.delete()
                print("Interaction closed by user.")
                return

            await message.edit(embed=create_commands_embed(current_page))

        except asyncio.TimeoutError:
            print("Command pagination timed out.")
            try:
                await message.clear_reactions()
                expired_embed = create_commands_embed(current_page)
                expired_embed.set_footer(text="This command navigation has expired.")
                expired_embed.color = discord.Color.greyple()
                await message.edit(embed=expired_embed)
            except discord.HTTPException:
                print("Could not clear reactions. Check bot permissions.")
            break
        except Exception as e:
            print(f"An unexpected error occurred during pagination: {e}")
            break
    
# --- Import Config Command ---
@client.command(name='import_config')
async def import_config(ctx: commands.Context):
    """
    Imports a new config.json file, overwriting the current one.
    Requires moderator permissions.
    Usage: !import_config (attach config.json file)
    """
    error_message_lifetime = 30

    # Helper to send a temporary error message
    async def send_temp_error(message_content: str):
        embed = discord.Embed(
            description=message_content,
            color=discord.Color.red()
        )
        embed.set_footer(text=f"This message will remove in {error_message_lifetime} seconds.")
        msg = await ctx.send(embed=embed)
        await asyncio.sleep(error_message_lifetime)
        try:
            await msg.delete()
        except discord.NotFound:
            pass

client.run(token)