import discord
from discord.ext import commands
from discord import ui, Interaction, Embed, Color
from discord import app_commands
import asyncio
from difflib import get_close_matches
import os
import json
from mistralai import Mistral
import secretsd as sec #TODO: switch to using environment variables or a more secure method for storing sensitive information
import time
from datetime import datetime
from textwrap import wrap
import random
import uuid

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

# Ensure 'stickynotes' key exists AFTER loading, for existing config files
if "stickynotes" not in config:
    config["stickynotes"] = {}
    with open("config.json", "w") as f:
        json.dump(config, f, indent=4)

# Stop flag for AI Chatbot
stop_flag = {}
command_list = []
channel_based_message_history = {}

# made it into a global constant
INTERNAL_COMMANDS = ["make_command", "set_info", "set_image", "moderators",
                         "remove_command", "add_bot_moderator", "rename_command",
                         "list_commands", "bot_config", "bot_commands", "edit",
                         "clear", "start_finetuning", "end_finetuning", "import_config",
                         "make_stickynote", "list_stickynote", "remove_stickynote", "stickynote",
                         "stop"]

def update_command_list():
    """Updates the global command_list from the current config."""
    global command_list
    global config

    with open("config.json", "r") as f:
        config.clear()
        config.update(json.load(f))

    command_list.clear()
    command_list.extend([cmd for cmd in config.keys() if cmd not in INTERNAL_COMMANDS])
    command_list.sort()

update_command_list()

client = commands.Bot(command_prefix='!', intents=intents, status=discord.Status.online,
                      activity=discord.Activity(type=discord.ActivityType.custom, name="Use !help or ping me!"))
client.remove_command("help")

# List of random messages for the !stop command
STOP_MESSAGES = [
    "Conversation ended. What's next?",
    "Stopping current dialogue....",
    "Affirmative. Previous context has been stopped.",
    "Chat session reset. How can I assist you now?",
    "Dialogue concluded. Ready for new instructions.",
    "OK, I was gagged by that.",
]

# --- Bot Events ---
@client.event
async def on_ready():
    """Called when the bot is ready and connected to Discord."""
    print(f"Logged in as {client.user.name}")
    print(f"Bot ID: {client.user.id}")
    print("Client has started")

@client.event
async def on_message(message: discord.Message):
    global stop_flag
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
                if attachment.filename.endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    mess["content"].append({"type": "image_url", "image_url": attachment.url})
                if attachment.filename.endswith((".txt", ".py", ".json", ".md")): # we can add more file types here if needed
                    attachment_content = str(await attachment.read())
                    mess["content"].append({"type": "text", "text": f"Attached file: {attachment_content}"})
        channel_based_message_history[channel_id].append(mess)
        full_output = "" # we use this to store the full output from the model, then we'll append this to the channel history
        current_message_content = "" #we will erase the content in this if the output is too long
        stop_flag[channel_id] = False # Clear the stop flag on new response
        async with message.channel.typing():
            main_message = await message.channel.send("...")
            response = await mistral_client.chat.stream_async(
            messages=channel_based_message_history[channel_id],\
            #TODO: use a custom fine-tuned model specific to OpenUtau, once trained
            model="mistral-medium-latest",
            temperature=0.7,
            safe_prompt=True,
            max_tokens=1000,
            top_p=0.95,
            )
            async for chunk in response:
                if chunk.data.choices[0].delta.content:
                    full_output += chunk.data.choices[0].delta.content
                    if len(current_message_content) + 3 > 2000:
                        current_message_content = chunk.data.choices[0].delta.content
                        main_message = await message.channel.send("...")
                    else:
                        current_message_content += chunk.data.choices[0].delta.content
                if chunk.data.choices[0].finish_reason != None:
                    await main_message.edit(content=current_message_content)
                    # Append the full output to the channel's history
                    channel_based_message_history[channel_id].append({"role": "assistant", "content": [{"type": "text", "text": full_output}]})
                    break
                if stop_flag.get(channel_id, False):
                    stop_flag[channel_id] = False
                    await main_message.edit(content=current_message_content + "-- (AI was Stopped by command)")
                    channel_based_message_history[channel_id].append({"role": "assistant", "content": [{"type": "text", "text": full_output + "-- (AI was Stopped by command)"}]})
                    break
                time_delta = last_sent - time.time()
                if abs(time_delta) < 0.9:
                    continue #restart the loop if it's not been about .9 seconds since the last message was sent/edited, to avoid rate limiting
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

@client.tree.command(name='stop', description='Stops the AI conversation in the current channel.')
async def stop(ctx: discord.Interaction):
    """
    Stops the current AI conversation
    Usage: !stop
    """
    global stop_flag

    channel_id = str(ctx.channel.id)

    if channel_id in channel_based_message_history:
        # Select a random message from the predefined list
        response_message = random.choice(STOP_MESSAGES)
        stop_flag[channel_id] = True
        await ctx.response.send_message(response_message)
        print(f"AI chat for channel {channel_id} stopped by {ctx.user.name}.")
    else:
        await ctx.response.send_message("There is no active AI conversation in this channel to stop.")
        print(f"Attempted to stop AI chat in {channel_id}, but no active history found.")

@client.command()
async def sync(ctx: commands.Context):
    """
    Syncs the bot's command list with the Discord server.
    """
    del1 = await ctx.send("Syncing commands...")
    await client.tree.sync()
    del2 = await ctx.send("Commands synced successfully!")
    await asyncio.sleep(5)  # Wait for a few seconds before deleting the message
    await del1.delete()
    await del2.delete()

async def send_temp_error(ctx: discord.Interaction, message_content: str, error_message_lifetime: int = 10):
        embed = discord.Embed(
            description=message_content,
            color=discord.Color.red()
        )
        embed.set_footer(text=f"This message will remove in {error_message_lifetime} seconds.")
        msg = await ctx.followup.send(embed=embed)
        await asyncio.sleep(error_message_lifetime)
        try:
            await msg.delete()
        except discord.NotFound:
            pass

# --- Bot Commands ---
@client.tree.command(name='set-image', description='Sets an image for a custom command.')
async def set_image(ctx: discord.Interaction, command: str, image: discord.Attachment):
    """
    Sets an image for a custom command.
    Requires moderator permissions.
    Usage: !set_image <command_name> (attach image)
    """
    if ctx.user.id not in config["moderators"]:
        await ctx.followup.send("You do not have permission to use this command.")
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

@client.tree.command(name='clear', description='Clears the channel\'s message history for the AI chat.')
async def clear(ctx: discord.Interaction):
    """
    Clears the channel's message history for the AI chat.
    Usage: !clear
    """
    channel_id = str(ctx.channel.id)
    if channel_id in channel_based_message_history:
        channel_based_message_history[channel_id] = []
        await ctx.followup.send("The message history for this channel has been cleared.")
    else:
        await ctx.followup.send("No message history found for this channel.")
    return

@client.tree.command(name='start-finetuning', description='Starts the finetuning process.')
async def start_finetuning(ctx: discord.Interaction):
    """
    Starts the finetuning process.
    """
    if ctx.user.id not in config.get("moderators", []):
        await ctx.followup.send("You do not have permission to use this command.")
        return
    await clear(ctx)  # Clear the message history before starting finetuning
    await ctx.followup.send("Starting Finetuning.")

@client.tree.command(name='end-finetuning', description='Ends the finetuning process.')
async def end_finetuning(ctx: discord.Interaction):
    """
    Ends the finetuning process by saving the current channel's chat history to a uniquely named JSON file.
    The file is saved in the 'finetuning-data' folder, which is created if it doesn't exist.
    """
    
    channel_id = str(ctx.channel.id)
    history = channel_based_message_history.get(channel_id, [])

    # Ensure the folder exists
    os.makedirs("finetuning-data", exist_ok=True)

    # Generate a unique filename using timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"finetuning-data/history_{channel_id}_{timestamp}.json"

    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=4, ensure_ascii=False)
        await ctx.followup.send(f"Finetuning ended. Chat history saved to `{filename}`.")
    except Exception as e:
        await ctx.followup.send(f"Failed to save chat history: {e}")

@client.tree.command(name='edit', description='Edits the last message the AI sent in the current channel.')
async def edit(ctx: discord.Interaction, *, new_content: str):
    """
    Edits the last message the AI sent in the current channel and updates the channel_based_message_history.
    Usage: !edit <new_content>
    """
    # Only allow moderators to use this command
    if ctx.user.id not in config.get("moderators", []):
        await ctx.followup.send("You do not have permission to use this command.")
        return

    channel_id = str(ctx.channel.id)
    last_ai_message = None

    # Find the last message sent by the bot in this channel
    async for msg in ctx.channel.history(limit=50):
        if msg.author == client.user:
            last_ai_message = msg
            break

    if last_ai_message:
        try:
            await last_ai_message.edit(content=new_content)
            # Update the last assistant message in channel_based_message_history
            if channel_id in channel_based_message_history:
                # Find the last assistant message in the history (search backwards)
                for entry in reversed(channel_based_message_history[channel_id]):
                    if entry.get("role") == "assistant":
                        entry["content"] = [{"type": "text", "text": new_content}]
                        break
            # Save the updated message history to disk (optional: you can choose a filename per channel)
            with open(f"history_{channel_id}.json", "w", encoding="utf-8") as f:
                json.dump(channel_based_message_history[channel_id], f, indent=4, ensure_ascii=False)
            await ctx.followup.send("The last AI message has been edited and the history has been updated.")
        except Exception as e:
            await ctx.followup.send(f"Failed to edit the message: {e}")
        return

    await ctx.followup.send("No recent AI message found to edit.")

@client.tree.command(name='set-info', description='Sets the informational text for a custom command.')
async def set_info(ctx: discord.Interaction, command: str, info: str):
    """
    Sets the informational text for a custom command.
    Requires moderator permissions.
    Usage: !set_info <command_name> <info_text>
    """
    if ctx.user.id not in config["moderators"]:
        await ctx.response.send_message("You do not have permission to use this command.")
        return

    conf = config.get(command, None)
    if conf is None:
        await ctx.response.send_message(f"The command `{command}` does not exist. Use `/make_command` to create it first.")
        return

    conf["info"] = info

    with open("config.json", "w") as f:
        json.dump(config, f, indent=4)

    update_command_list()
    await ctx.send(f"The info for the command `{command}` has been set successfully!")

@client.tree.command(name='make-command', description='Creates a new custom command.')
@app_commands.describe(
    command="The name of the command to create",
    info="Optional informational text for the command (if not provided, an image must be attached)",
    attachment="Optional image attachment for the command (if not provided, info must be given)"
)
async def make_command(ctx: discord.Interaction, command: str, info: str = None, attachment: discord.Attachment = None):
    """
    Creates a new custom command.
    Requires moderator permissions.
    Usage: !make_command <command_name> [info_text] (attach image)
    """
    if ctx.user.id not in config["moderators"]:
        await ctx.response.send_message("You do not have permission to use this command.")
        return

    if command in config:
        await ctx.response.send_message(f"The command `{command}` already exists.")
        return
    #why did i have to code it this way.
    if attachment:
        has_image = True
    else: has_image = False

    if not has_image and not info:
        await ctx.response.send_message("You must provide either an info message, an image, or both.")
        return

    config[command] = {"info": info, "has_image": has_image}

    if has_image:
        image_filename = command + ".png"
        image_path = os.path.join("images", image_filename)
        os.makedirs(os.path.dirname(image_path), exist_ok=True)
        await attachment.save(image_path)
        config[command]["image"] = image_path

    with open("config.json", "w") as f:
        json.dump(config, f, indent=4)

    update_command_list()
    await ctx.response.send_message(f"The command `{command}` has been created successfully!")

@client.tree.command(name='remove-command', description='Removes an existing custom command.')
async def remove_command(ctx: discord.Interaction, command: str): 
    """
    Removes an existing custom command.
    Requires moderator permissions.
    Usage: !remove_command <command_name>
    """
    if ctx.user.id not in config["moderators"]:
        await ctx.response.send_message("You do not have permission to use this command.")
        return
    if command not in config:
        await ctx.response.send_message(f"The command `{command}` does not exist.")
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

@client.tree.command(name='add-bot-moderator', description='Adds a user as a bot moderator.')
@app_commands.describe(user="The user to add as a moderator")
async def add_bot_moderator(ctx: discord.Interaction, user: discord.User): 
    """
    Adds a user as a bot moderator.
    Requires existing moderator permissions.
    Usage: !add_bot_moderator <@user>
    """
    if ctx.user.id not in config["moderators"]:
        await ctx.response.send_message("You do not have permission to use this command.")
        return

    if user.id in config["moderators"]:
        await ctx.response.send_message(f"{user.name} is already a moderator.")
        return

    config["moderators"].append(user.id)
    with open("config.json", "w") as f:
        json.dump(config, f, indent=4)

    await ctx.response.send_message(f"{user.name} has been added as a moderator.")

@client.tree.command(name='moderators', description='Lists all current bot moderators.')
async def moderators(ctx: discord.Interaction): 
    """
    Lists all current bot moderators.
    Requires moderator permissions.
    Usage: !moderators
    """
    if ctx.user.id not in config["moderators"]:
        await ctx.response.send_message("You do not have permission to use this command.")
        return

    moderator_ids = config["moderators"]
    if not moderator_ids:
        await ctx.response.send_message("No moderators have been added yet.")
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
        await ctx.followup.send(embed=embed)

@client.tree.command(name='rename-command', description='Renames an existing custom command.')
@app_commands.rename(old_name="old-command", new_name="new-command")
@app_commands.describe(
    old_name="The current name of the command to rename",
    new_name="The new name for the command"
)
async def rename_command(ctx: discord.Interaction, old_name: str, new_name: str): 
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

class CommandPaginator(ui.View):
    def __init__(self, interaction: Interaction, command_pages, embed_color, embed_title_prefix, no_results_message, ephemeral: bool):
        super().__init__(timeout=60)
        self.interaction = interaction
        self.command_pages = command_pages
        self.total_pages = len(command_pages)
        self.current_page = 0
        self.embed_color = embed_color
        self.embed_title_prefix = embed_title_prefix
        self.no_results_message = no_results_message
        self.ephemeral = ephemeral

    def create_embed(self):
        commands_on_page = self.command_pages[self.current_page]
        commands_str = "\n".join(commands_on_page)

        title = self.embed_title_prefix or "Available Commands"
        description = (
            self.no_results_message
            if not commands_on_page
            else f"Here are the commands you can use:\n\n{commands_str}"
        )

        embed = Embed(title=title, description=description, color=self.embed_color)
        embed.set_footer(text=f"Page {self.current_page + 1}/{self.total_pages}")
        return embed

    @ui.button(label="◀️ Prev", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: Interaction, button: ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @ui.button(label="▶️ Next", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: Interaction, button: ui.Button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            await interaction.response.edit_message(embed=self.create_embed(), view=self)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        try:
            await self.interaction.edit_original_response(view=self)
        except Exception:
            pass  # In case interaction is already gone

@client.tree.command(name='list-commands', description='Lists all user-defined custom commands.')
@app_commands.describe(
    page_or_filter="Page number or search query (optional)",
    ephemeral="If true, only you can see the command output (other users cannot see or interact with it). Default: true."
)
@app_commands.rename(page_or_filter="page-or-filter")
async def list_commands(
    interaction: discord.Interaction,
    page_or_filter: str = None,
    ephemeral: bool = True
):
    await interaction.response.defer(ephemeral=ephemeral)
    update_command_list()

    COMMANDS_PER_PAGE = 10

    # Determine if it's a search or a page number
    if page_or_filter and not page_or_filter.isdigit():
        search_query = page_or_filter
        commands_to_display_base = autocorrect_command(search_query)
        embed_title_prefix = f"User-Defined Commands matching '{search_query}'"
        no_results_message = f"No user-defined commands matching '{search_query}' were found."
        embed_color = Color.blue()
    else:
        commands_to_display_base = command_list
        embed_title_prefix = "Available Commands"
        no_results_message = "It seems there are no user-defined commands to display yet."
        embed_color = Color.green()

    if not commands_to_display_base:
        embed = Embed(
            title="No User-Defined Commands Available" if not page_or_filter else "No Commands Found",
            description=no_results_message,
            color=Color.red()
        )
        embed.set_footer(text="This message will disappear in 60 seconds.")
        await interaction.followup.send(embed=embed, ephemeral=ephemeral)
        return

    command_pages, _ = split_list(commands_to_display_base, COMMANDS_PER_PAGE)

    view = CommandPaginator(
        interaction=interaction,
        command_pages=command_pages,
        embed_color=embed_color,
        embed_title_prefix=embed_title_prefix,
        no_results_message=no_results_message,
        ephemeral=ephemeral
    )

    await interaction.followup.send(embed=view.create_embed(), view=view, ephemeral=ephemeral)
    
# --- Import Config Command ---
@client.tree.command(name='import-config', description='Dev use only: Imports a new config.json file, overwriting the current one.')
async def import_config(ctx: discord.Interaction, file: discord.Attachment):
    """Imports a new config.json file, overwriting the current one."""

    # Only allow moderators to run this command
    if ctx.user.id not in config.get("moderators", []):
        await send_temp_error(ctx, "You do not have permission to use this command.")
        return
    
    try:
        file_bytes = await file.read()
        new_config = json.loads(file_bytes.decode("utf-8"))
    except Exception as e:
        await send_temp_error(ctx, f"Failed to read config: {e}")
        return

    # Update in-memory config and save to disk
    config.clear()
    config.update(new_config)
    with open("config.json", "w") as f:
        json.dump(config, f, indent=4)

    update_command_list()
    await ctx.followup.send("Configuration imported successfully.")

# --- NEW COMMANDS: Sticky Notes ---

@client.command(name='make_stickynote')
async def make_stickynote(ctx: commands.Context, name: str):
    """
    Creates a sticky note from a replied message.
    Requires moderator permissions.
    Usage: !make_stickynote <note_name> (reply to a message)
    """
    error_message_lifetime = 30
    media_dir = "stickynote_media" # Directory to save media files

    if ctx.author.id not in config["moderators"]:
        msg = await ctx.send("You do not have permission to use this command.")
        await asyncio.sleep(error_message_lifetime)
        try: await msg.delete()
        except discord.NotFound: pass
        return

    if not ctx.message.reference or not ctx.message.reference.message_id:
        msg = await ctx.send("You must reply to a message to make it a sticky note.")
        await asyncio.sleep(error_message_lifetime)
        try: await msg.delete()
        except discord.NotFound: pass
        return

    try:
        replied_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
    except discord.NotFound:
        msg = await ctx.send("The message you replied to could not be found.")
        await asyncio.sleep(error_message_lifetime)
        try: await msg.delete()
        except discord.NotFound: pass
        return
    except discord.HTTPException as e:
        msg = await ctx.send(f"An error occurred while fetching the replied message: `{e}`")
        await asyncio.sleep(error_message_lifetime)
        try: await msg.delete()
        except discord.NotFound: pass
        return

    if name in config["stickynotes"]:
        msg = await ctx.send(f"A sticky note with the name `{name}` already exists. Please choose a different name or remove the existing one.")
        await asyncio.sleep(error_message_lifetime)
        try: await msg.delete()
        except discord.NotFound: pass
        return

    # Store the sticky note data
    note_data = {
        "content": replied_message.content,
        "author_id": replied_message.author.id,
        "author_name": replied_message.author.display_name,
        "channel_id": replied_message.channel.id,
        "message_id": replied_message.id,
        "timestamp": replied_message.created_at.isoformat(),
        "media_url": None, # Will store URL if media is detected and saved
        "media_type": None # "image", "audio", "video"
    }

    # Handle attachments from the replied message
    if replied_message.attachments:
        attachment = replied_message.attachments[0] # Only take the first attachment for now
        file_extension = os.path.splitext(attachment.filename)[1].lower()
        
        # Check for image types
        if attachment.content_type.startswith('image/'):
            media_type = "image"
        # Check for audio types
        elif attachment.content_type.startswith('audio/'):
            media_type = "audio"
        # Check for video types
        elif attachment.content_type.startswith('video/'):
            media_type = "video"
        else:
            media_type = None # Unsupported media type

        if media_type:
            os.makedirs(media_dir, exist_ok=True)
            # Create a unique filename using UUID to prevent conflicts
            unique_filename = f"{uuid.uuid4()}{file_extension}"
            media_path = os.path.join(media_dir, unique_filename)
            
            try:
                await attachment.save(media_path)
                note_data["media_url"] = media_path # Store local path
                note_data["media_type"] = media_type
                print(f"Saved sticky note media to: {media_path}")
            except Exception as e:
                print(f"Error saving sticky note media {attachment.filename}: {e}")
                note_data["media_url"] = None # Reset if save failed
                note_data["media_type"] = None
                await ctx.send(f"Warning: Could not save the attached media for sticky note `{name}`. It will be text-only.")

    config["stickynotes"][name] = note_data

    with open("config.json", "w") as f:
        json.dump(config, f, indent=4)

    embed = discord.Embed(
        title=f"Sticky Note '{name}' Created",
        description=f"Saved message from {replied_message.author.display_name}:\n>>> {replied_message.content[:500]}{'...' if len(replied_message.content) > 500 else ''}",
        color=discord.Color.gold()
    )
    embed.add_field(name="Original Message Link", value=f"[Go to message]({replied_message.jump_url})", inline=False)
    if note_data["media_url"] and note_data["media_type"] == "image":
        embed.set_image(url=f"attachment://{os.path.basename(note_data['media_url'])}") # Use attachment for local file
    
    # Send the embed and any attached media file
    files_to_send = []
    if note_data["media_url"] and note_data["media_type"] == "image":
        files_to_send.append(discord.File(note_data["media_url"], filename=os.path.basename(note_data["media_url"])))

    await ctx.send(embed=embed, files=files_to_send if files_to_send else None)


@client.command(name='list_stickynote')
async def list_stickynote(ctx: commands.Context, *, page_or_filter: str = None):
    """
    Lists all saved sticky notes.
    Requires moderator permissions.
    Usage: !list_stickynote [page_number|search_query]
    """
    error_message_lifetime = 30

    if ctx.author.id not in config["moderators"]:
        msg = await ctx.send("You do not have permission to use this command.")
        await asyncio.sleep(error_message_lifetime)
        try: await msg.delete()
        except discord.NotFound: pass
        return

    all_stickynote_names = sorted(list(config["stickynotes"].keys()))
    COMMANDS_PER_PAGE = 10

    if page_or_filter and not page_or_filter.isdigit():
        search_query = page_or_filter.lower()
        commands_to_display_base = [name for name in all_stickynote_names if search_query in name.lower()]
        embed_title_prefix = f"Sticky Notes matching '{search_query}'"
        no_results_message = f"No sticky notes matching '{search_query}' were found."
        initial_page_index = 0
        embed_color = discord.Color.purple()
    else:
        commands_to_display_base = all_stickynote_names
        embed_title_prefix = "All Sticky Notes"
        no_results_message = "It seems there are no sticky notes saved yet."
        embed_color = discord.Color.gold()
        initial_page_index = 0

        if page_or_filter and page_or_filter.isdigit():
            try:
                requested_page = int(page_or_filter) - 1
                initial_page_index = requested_page
            except ValueError:
                pass

    if not commands_to_display_base:
        embed = discord.Embed(
            title="No Sticky Notes Available" if not page_or_filter else "No Sticky Notes Found",
            description=no_results_message,
            color=discord.Color.red()
        )
        embed.set_footer(text="This message will disappear in 60 seconds.")
        msg = await ctx.send(embed=embed)
        await asyncio.sleep(60)
        try: await msg.delete()
        except discord.NotFound: pass
        return

    command_pages, num_pages = split_list(commands_to_display_base, COMMANDS_PER_PAGE)

    current_page = initial_page_index
    if not (0 <= current_page < num_pages):
        current_page = 0
        embed_title_prefix = "Invalid Page Number"
        no_results_message = f"Page number must be between 1 and {num_pages}. Showing page 1 instead."
        embed_color = discord.Color.red()


    def create_stickynote_embed(page_idx, total_pages_count, current_names_list, initial_color, title_prefix, no_results_msg):
        if not current_names_list or not (0 <= page_idx < len(current_names_list)):
            return discord.Embed(
                title="Error Displaying Sticky Notes",
                description="Could not find sticky notes for this page.",
                color=discord.Color.red()
            )

        names_on_page = current_names_list[page_idx]
        
        description_lines = []
        if title_prefix == "Invalid Page Number":
            description_lines.append(no_results_msg)
            description_lines.append("\n")

        for name in names_on_page:
            note_data = config["stickynotes"].get(name)
            if note_data:
                content_snippet = note_data['content'][:100] + '...' if len(note_data['content']) > 100 else note_data['content']
                jump_url = f"https://discord.com/channels/{ctx.guild.id}/{note_data['channel_id']}/{note_data['message_id']}"
                media_info = ""
                if note_data.get("media_type"):
                    media_info = f" ({note_data['media_type'].capitalize()} attached)"
                
                description_lines.append(f"**`{name}`** (from {note_data['author_name']}){media_info}: {content_snippet}")
                description_lines.append(f"[Link]({jump_url})")
            else:
                description_lines.append(f"**`{name}`** (Note data missing)")
        
        embed = discord.Embed(
            title=title_prefix,
            description="\n".join(description_lines),
            color=initial_color
        )
        embed.set_footer(text=f"Page {page_idx + 1}/{total_pages_count} | React to navigate. This message will expire in 60 seconds.")
        return embed

    message = await ctx.send(embed=create_stickynote_embed(current_page, num_pages, command_pages, embed_color, embed_title_prefix, no_results_message))

    if num_pages > 1:
        await message.add_reaction("◀️")
        await message.add_reaction("▶️")
        await message.add_reaction("❌")
    else:
        await message.add_reaction("❌")

    def check_reaction(reaction, user):
        return (user == ctx.author and
                str(reaction.emoji) in ["◀️", "▶️", "❌"] and
                reaction.message.id == message.id)

    while True:
        try:
            reaction, user = await client.wait_for("reaction_add", timeout=60.0, check=check_reaction)

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
                print("Sticky note interaction closed by user.")
                return

            await message.edit(embed=create_stickynote_embed(current_page, num_pages, command_pages, embed_color, embed_title_prefix, no_results_message))

        except asyncio.TimeoutError:
            print("Sticky note pagination timed out.")
            try:
                await message.clear_reactions()
                expired_embed = create_stickynote_embed(current_page, num_pages, command_pages, embed_color, embed_title_prefix, no_results_message)
                expired_embed.set_footer(text="This command navigation has expired.")
                expired_embed.color = discord.Color.greyple()
                await message.edit(embed=expired_embed)
            except discord.HTTPException:
                print("Could not clear reactions. Check bot permissions.")
            break
        except Exception as e:
            print(f"An unexpected error occurred during sticky note pagination: {e}")
            break

@client.command(name='remove_stickynote')
async def remove_stickynote(ctx: commands.Context, name: str):
    """
    Removes a sticky note by its name.
    Requires moderator permissions.
    Usage: !remove_stickynote <note_name>
    """
    error_message_lifetime = 30
    media_dir = "stickynote_media"

    if ctx.author.id not in config["moderators"]:
        msg = await ctx.send("You do not have permission to use this command.")
        await asyncio.sleep(error_message_lifetime)
        try: await msg.delete()
        except discord.NotFound: pass
        return

    if name not in config["stickynotes"]:
        msg = await ctx.send(f"Sticky note `{name}` does not exist.")
        await asyncio.sleep(error_message_lifetime)
        try: await msg.delete()
        except discord.NotFound: pass
        return

    # Delete associated media file if it exists
    note_data = config["stickynotes"][name]
    if note_data.get("media_url") and os.path.exists(note_data["media_url"]):
        try:
            os.remove(note_data["media_url"])
            print(f"Removed sticky note media file: {note_data['media_url']}")
        except OSError as e:
            print(f"Error removing sticky note media file {note_data['media_url']}: {e}")

    del config["stickynotes"][name]

    with open("config.json", "w") as f:
        json.dump(config, f, indent=4)

    await ctx.send(f"Sticky note `{name}` has been successfully removed.")

# --- NEW COMMAND: !stickynote ---
@client.command(name='stickynote')
async def stickynote(ctx: commands.Context, name: str):
    """
    Retrieves and displays a saved sticky note by its name.
    Usage: !stickynote <note_name>
    """
    error_message_lifetime = 30

    note_data = config["stickynotes"].get(name)

    if not note_data:
        msg = await ctx.send(f"Sticky note `{name}` not found. Use `!list_stickynote` to see available notes.")
        await asyncio.sleep(error_message_lifetime)
        try: await msg.delete()
        except discord.NotFound: pass
        return

    jump_url = f"https://discord.com/channels/{ctx.guild.id}/{note_data['channel_id']}/{note_data['message_id']}"

    embed = discord.Embed(
        title=f"Sticky Note: '{name}'",
        description=note_data['content'],
        color=discord.Color.gold()
    )
    embed.add_field(name="Original Author:", value=note_data['author_name'], inline=True)
    embed.add_field(name="Date:", value=f"<t:{int(datetime.fromisoformat(note_data['timestamp']).timestamp())}:F>", inline=True)
    embed.add_field(name="Original Message Link:", value=f"[Click to jump]({jump_url})", inline=False) # Direct link

    files_to_send = []
    if note_data.get("media_url") and os.path.exists(note_data["media_url"]):
        file_path = note_data["media_url"]
        file_type = note_data.get("media_type")

        # For images, set as embed image and attach file
        if file_type == "image":
            filename = os.path.basename(file_path)
            embed.set_image(url=f"attachment://{filename}")
            files_to_send.append(discord.File(file_path, filename=filename))
        # For audio/video, attach the file and mention it in a field
        elif file_type in ["audio", "video"]:
            filename = os.path.basename(file_path)
            files_to_send.append(discord.File(file_path, filename=filename))
            embed.add_field(name="Attached Media", value=f"Contains an attached {file_type} file: `{filename}`", inline=False)
    elif note_data.get("media_url") and not os.path.exists(note_data["media_url"]):
        embed.set_footer(text="Note: Associated media file not found on server.")

    await ctx.send(embed=embed, files=files_to_send if files_to_send else None)

client.run(token)
