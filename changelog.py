"""GitHub-backed OpenUtau changelogs, independent of bot credentials/configuration."""
from dataclasses import dataclass
import asyncio
import io
import os
import re
from urllib.parse import quote

import aiohttp
import discord
from discord import app_commands

from localization import catalog
from translations import localized

REPOSITORY = "https://github.com/openutau/OpenUtau"
API = "https://api.github.com/repos/openutau/OpenUtau"
VERSION = re.compile(r"(?:v)?\d+(?:\.\d+){2,3}(?:-(?:alpha|beta|stable)(?:[.\d]*))?", re.I)


class ChangelogError(Exception):
    """An error safe to display to the command's caller."""


def attachment_chunks(data, limit):
    """Keep each split text attachment valid UTF-8, including at size boundaries."""
    start = 0
    while start < len(data):
        end = min(start + limit, len(data))
        while end < len(data) and data[end] & 0xC0 == 0x80:
            end -= 1
        if end == start:
            raise ValueError("Attachment limit cannot hold one UTF-8 character")
        yield data[start:end]
        start = end


def normalize_version(value):
    return value.casefold().removeprefix("build/").removeprefix("v")


def release_channel(release):
    label = f"{release['tag_name']} {release.get('name') or ''}".casefold()
    for channel in ("alpha", "beta"):
        if re.search(rf"\b{channel}\b", label):
            return channel
    return "beta" if release.get("prerelease") else "stable"


@dataclass
class Changelog:
    label: str
    url: str
    head: str
    commits: list

    def attachment(self):
        lines = [f"OpenUtau: {self.label}", self.url, f"Target release commit: {self.head}", ""]
        for item in self.commits:
            commit = item["commit"]
            author = commit.get("author") or {}
            lines.extend([f"{item['sha']} | {author.get('name', 'Unknown')} | {author.get('date', '')}",
                          commit["message"], f"{REPOSITORY}/commit/{item['sha']}", ""])
        if not self.commits:
            lines.append("No changes between these releases.")
        return "\n".join(lines).encode("utf-8")

    def pages(self):
        # Commit subjects are bounded for embeds; the attachment preserves full messages.
        pages, lines, size = [], [], 0
        for item in reversed(self.commits):
            subject = item["commit"]["message"].splitlines()[0] if item["commit"]["message"] else "(no message)"
            subject = discord.utils.escape_markdown(discord.utils.escape_mentions(subject[:500]))
            line = f"• [`{item['sha'][:7]}`]({REPOSITORY}/commit/{item['sha']}) {subject}"
            if size + len(line) + 1 > 3500:
                pages.append("\n".join(lines))
                lines, size = [], 0
            lines.append(line)
            size += len(line) + 1
        if lines:
            pages.append("\n".join(lines))
        return pages or [""]


class GitHub:
    def __init__(self, session):
        self.session = session
        self._releases = None

    async def get(self, path, **params):
        async with self.session.get(API + path, params=params) as response:
            if response.status in (403, 429):
                raise ChangelogError("GitHub denied the request or its rate limit was reached. Please try again later.")
            if response.status == 404:
                raise ChangelogError("That release or commit could not be found in openutau/OpenUtau.")
            if response.status != 200:
                raise ChangelogError(f"GitHub could not provide the changelog (HTTP {response.status}). Please try again later.")
            return await response.json()

    async def published_releases(self):
        # One snapshot per request keeps release selection consistent across pages.
        if self._releases is None:
            published, page = [], 1
            while True:
                releases = await self.get("/releases", per_page=100, page=page)
                published.extend(r for r in releases if not r.get("draft"))
                if len(releases) < 100:
                    break
                page += 1
            self._releases = sorted(published, key=lambda r: r.get("published_at") or "", reverse=True)
        return self._releases

    async def release(self, selector, previous=False):
        channel = selector if selector in ("alpha", "beta", "stable") else None
        if selector and not channel and not VERSION.fullmatch(selector):
            raise ChangelogError("Enter a version such as 0.1.569 or 0.1.570.12-alpha, or alpha, beta, stable.")
        matches = []
        for release in await self.published_releases():
            tag = normalize_version(release["tag_name"])
            version = normalize_version(selector)
            if not selector:
                match = True
            elif channel:
                match = release_channel(release) == channel
            else:
                # Prefer an exact tag; a bare version also accepts its channel suffix.
                match = tag == version or tag.split("-", 1)[0] == version
            if match:
                matches.append(release)
        if not matches:
            if not selector:
                raise ChangelogError("No published OpenUtau releases were found.")
            raise ChangelogError(f"No published OpenUtau release matches '{selector}'. Check the version or release channel.")
        matches.sort(key=lambda r: (
            bool(selector) and not channel and normalize_version(r["tag_name"]) == normalize_version(selector),
            r.get("published_at") or ""), reverse=True)
        if previous and len(matches) < 2:
            raise ChangelogError("A previous published release is required to show changes between releases.")
        return matches[1 if previous else 0]

    async def changelog(self, since=None):
        selector = (since or "").strip().casefold()
        current = await self.release("")
        release = await self.release(selector, previous=not selector)
        head = await self.get("/commits/" + quote(current["tag_name"], safe=""))
        base = await self.get("/commits/" + quote(release["tag_name"], safe=""))
        comparison = f"{base['sha']}...{head['sha']}"
        commits, page = [], 1
        while True:
            data = await self.get("/compare/" + comparison, per_page=100, page=page)
            if data["status"] in ("diverged", "behind"):
                raise ChangelogError("The starting release is not an ancestor of the current release; a complete release comparison cannot be produced.")
            commits.extend(data["commits"])
            if len(commits) >= data["total_commits"]:
                break
            if not data["commits"]:
                raise ChangelogError("GitHub returned an incomplete comparison. Please try again later.")
            page += 1
        return Changelog(f"{release['tag_name']} → {current['tag_name']}", f"{REPOSITORY}/compare/{comparison}", head["sha"], commits)


async def fetch_changelog(since=None):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "OpenUtau-Discord-Bot",
               "X-GitHub-Api-Version": "2022-11-28"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    try:
        async with aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as session:
            return await asyncio.wait_for(GitHub(session).changelog(since), timeout=120)
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        raise ChangelogError("GitHub could not be reached in time. Please try again later.") from exc


class ChangelogView(discord.ui.View):
    def __init__(self, interaction, result):
        super().__init__(timeout=180)
        self.interaction, self.result = interaction, result
        self.pages, self.index = result.pages(), 0
        self.message = None
        self.previous.label = catalog.text("messages.previous-page", interaction.locale)
        self.next.label = catalog.text("messages.next-page", interaction.locale)
        self.update_buttons()

    def update_buttons(self):
        self.previous.disabled = self.index == 0
        self.next.disabled = self.index == len(self.pages) - 1

    def embed(self):
        embed = discord.Embed(title=f"OpenUtau — {self.result.label}", url=self.result.url,
                              description=self.pages[self.index] or "No changes between these releases.",
                              color=discord.Color.blue())
        embed.set_footer(text=f"{len(self.result.commits)} commits • Page {self.index + 1}/{len(self.pages)} • release {self.result.head[:7]}")
        return embed

    async def interaction_check(self, interaction):
        if interaction.user.id == self.interaction.user.id:
            return True
        await interaction.response.send_message("Run /changelog to browse your own results.", ephemeral=True)
        return False

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction, button):
        self.index = max(0, self.index - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next(self, interaction, button):
        self.index = min(len(self.pages) - 1, self.index + 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


async def send_changelog(interaction, since=None):
    await interaction.response.defer(thinking=True)
    try:
        result = await fetch_changelog(since)
    except ChangelogError as exc:
        await interaction.followup.send(str(exc), ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
        return
    view = ChangelogView(interaction, result)
    # Split exceptionally large logs losslessly to respect the server upload limit.
    data = result.attachment()
    limit = getattr(interaction.guild, "filesize_limit", 10 * 1024 * 1024)
    chunks = list(attachment_chunks(data, limit))
    for offset in range(0, len(chunks), 10):
        files = [discord.File(io.BytesIO(chunk), filename=f"changelog-{offset + i + 1}.txt")
                 for i, chunk in enumerate(chunks[offset:offset + 10])]
        kwargs = {"embed": view.embed(), "view": view} if offset == 0 else {}
        message = await interaction.followup.send(files=files, wait=True,
                                                  allowed_mentions=discord.AllowedMentions.none(), **kwargs)
        if offset == 0:
            view.message = message


def register_changelog(tree):
    @tree.command(name="changelog", description=localized("commands.changelog.description"))
    @app_commands.describe(since=localized("commands.changelog.since"))
    @app_commands.checks.cooldown(1, 15, key=lambda interaction: interaction.user.id)
    async def changelog(interaction: discord.Interaction, since: app_commands.Range[str, 1, 100] = None):
        await send_changelog(interaction, since)

    @changelog.autocomplete("since")
    async def autocomplete(interaction, current):
        return [app_commands.Choice(name=channel, value=channel)
                for channel in ("alpha", "beta", "stable") if current.casefold() in channel]

    @changelog.error
    async def on_error(interaction, error):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(f"Please wait {error.retry_after:.0f}s before requesting another changelog.", ephemeral=True)
        else:
            raise error
