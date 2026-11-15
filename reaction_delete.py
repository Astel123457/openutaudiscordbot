"""Allow bot moderators to use a cross-mark reaction to dismiss this bot's messages, cached or not."""
import logging

import discord

logger = logging.getLogger(__name__)


def register_reaction_delete(client, get_config):
    @client.listen('on_raw_reaction_add')
    async def delete_on_cross(payload):
        if client.user is None or payload.user_id == client.user.id:
            return
        if payload.user_id not in get_config().get('moderators', []):
            return
        if payload.emoji.id is not None or payload.emoji.name.rstrip('\ufe0f') != '❌':
            return
        try:
            channel = client.get_channel(payload.channel_id)
            if channel is None:
                channel = await client.fetch_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            if message.author.id == client.user.id and payload.user_id in get_config().get('moderators', []):
                await message.delete()
        except discord.NotFound:
            pass  # Already deleted, including simultaneous reactions.
        except discord.HTTPException as exc:
            logger.warning('Could not dismiss bot message %s (%s)', payload.message_id, type(exc).__name__)
