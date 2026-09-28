# OpenUtau changelog command

Restart the bot to register `/changelog` through its existing startup command sync.

| Command | Result |
| --- | --- |
| `/changelog` | Changes from the previous published release to the current published release. |
| `/changelog since:0.1.569` | Changes from the matching release to the current release. |
| `/changelog since:0.1.570.12-alpha` | Changes from that exact prerelease to the current release. |
| `/changelog since:alpha` | Changes from the latest alpha to the current release. |
| `/changelog since:beta` | Changes from the latest beta to the current release. |
| `/changelog since:stable` | Changes from the latest stable release to the current release. |

The current release is the most recently published release across all channels,
including prereleases. The default baseline is the release published immediately
before it. Unreleased commits on master are excluded. An explicit starting release
that is already the current release produces an empty changelog.

Version inputs must match an existing published release. Three- and four-part
versions are supported, with an optional `v` prefix and alpha/beta/stable suffix.
Historical `build/` tags are resolved from their version number. Channel lookup
checks both release names and tags; otherwise a prerelease counts as beta and a
regular release as stable. Drafts are excluded.

Results contain commit subjects, newest first, with GitHub links and Previous/Next
buttons. Only the requester can navigate; buttons expire after three minutes.
The attached text file preserves all full commit messages, oldest first, and
remains available after the buttons expire. Very large files are split into
numbered parts. The commit used as the release baseline is excluded. Both ends
of a comparison are pinned to commit hashes before fetching all comparison pages.
This is a commit log, not an AI-generated summary; merge commits are included.

GitHub requests use `aiohttp` (also installed by `discord.py`). An optional
`GITHUB_TOKEN` environment variable enables authenticated GitHub rate limits;
the public repository does not require a token. Requests have timeouts and a
15-second per-user cooldown. Missing releases, rate limits, and releases that
are not ancestors of the current release produce explanatory errors instead of partial logs.

Validation: `python -m unittest discover -s tests -v` from the bot directory.
