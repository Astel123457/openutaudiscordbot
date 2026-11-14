"""Opt-in, report-only Mistral moderation experiment."""
import asyncio
import logging

import discord
from discord.ext import commands

MODEL = 'mistral-moderation-2603'
CONFIG_KEY = 'moderation_channels'
logger = logging.getLogger(__name__)


async def report_message(message, mistral, enabled):
    if not enabled() or not message.content.strip():
        return
    try:
        response = await asyncio.wait_for(
            mistral.classifiers.moderate_async(model=MODEL, inputs=message.content, timeout_ms=15000),
            timeout=20,
        )
        if not response.results or response.results[0].categories is None:
            raise ValueError('Missing moderation categories')
        result = response.results[0]
        flagged = [name for name, value in result.categories.items() if value]
        if not flagged or not enabled():
            return
        lines = []
        for name in flagged:
            label = discord.utils.escape_markdown(discord.utils.escape_mentions(name))
            score = (result.category_scores or {}).get(name)
            lines.append(f'• {label}' + (f' (score: {score:.3f})' if score is not None else ''))
        embed = discord.Embed(title='Message flagged! Reason(s) listed below', description='\n'.join(lines), color=discord.Color.orange())
        await message.reply(embed=embed, mention_author=False, allowed_mentions=discord.AllowedMentions.none(), silent=True)
    except Exception as exc:
        # Do not print exception bodies: SDK errors may include the original message.
        logger.warning('Moderation test failed for message %s (%s)', message.id, type(exc).__name__)


def register_moderation(client, mistral, get_config, save_config):
    @client.listen('on_message')
    async def moderation_listener(message):
        # Ignore our own reports (and all other messages from this bot) to avoid loops.
        if message.author == client.user:
            return
        enabled = lambda: str(message.channel.id) in get_config().get(CONFIG_KEY, [])
        await report_message(message, mistral, enabled)

    @client.command(name='moderation')
    async def moderation(ctx: commands.Context, action: str = 'status'):
        config = get_config()
        if ctx.author.id not in config.get('moderators', []):
            await ctx.send('Only bot moderators can configure the moderation test.')
            return
        action = action.casefold()
        if action not in ('on', 'off', 'status'):
            await ctx.send('Usage: !moderation on | off | status (for this channel).')
            return
        channel_id = str(ctx.channel.id)
        channels = set(config.get(CONFIG_KEY, []))
        if action == 'on':
            channels.add(channel_id)
        elif action == 'off':
            channels.discard(channel_id)
        if action != 'status':
            config[CONFIG_KEY] = sorted(channels)
            save_config()
        state = 'enabled' if channel_id in channels else 'disabled'
        await ctx.send(f'Moderation test is {state} in this channel. When enabled, message text is sent to Mistral; flagged categories are reported in a reply. No moderation actions are taken.', allowed_mentions=discord.AllowedMentions.none())
