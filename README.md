# tgcf - Telegram Control Foundation

A customized version of `tgcf` for automated telegram message forwarding.

## Features
- Filter messages based on text, users, or file types.
- **Source-Specific Plugins**: configure custom plugins (whitelist, blacklist, filter, text replacement, caption style, etc.) for each connection separately.
- Supports protected chats (gracefully skips restricted content).
- Gracefully handles unavailable or missing source channels by skipping them and reporting errors at the end.
- Robust ID handling for different Telegram peer formats.
- **Resilient mode**: automatically reconnects and resumes after network outages (`tgcf past --resilient`).
- **Multiple Sessions**: configure alternate accounts to bypass `FloodWait` limits.
- **Smart Channel Sorting**: automatically prioritizes processing highly-restricted channels first to maximize account availability before rate limits hit.
- Native Batch Forwarding: automatically groups up to 100 messages per API call if no modifying plugins are active, drastically reducing rate limits.
- **Auto-sync Channel Names**: automatically fetches and updates the actual Telegram channel names (`source_name` and `dest_names`) in `tgcf.config.json` on every run.
- **Dynamic Proxy Rotation & Health Tracking**: automatically tests and rotates between user-defined and public MTProto proxies to bypass regional Telegram bans. Instantly prunes non-working proxies from the local cache file to keep it clean.
- Detailed logging: shows real Telegram channel names, message links for FloodWait retries, and a full summary on completion.

## Docs
- [Setup](docs/setup.md)
- [Usage](docs/usage.md) (past/live modes, dry run)
- [Configuration reference](docs/configuration.md)
- [Scheduled execution](docs/scheduling.md) (GitHub Actions, cron, NTFS troubleshooting)
- [Changelog](docs/changelog.md)
