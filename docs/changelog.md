# Changelog

## 2026-06-19
- feat(proxy): implement dynamic proxy rotation and MTProto/SOCKS auto-fallback
- feat(proxy): track proxy health and instantly prune dead proxies (failures >= 3) from the local cache (`tgcf.proxies.json`)
- feat(proxy): introduce `--proxy-check-timeout` and `--direct-check-timeout` options (and env variables) for customizable socket checks
- fix(telethon): resolve indefinite hang during client connect phase by configuring `auto_reconnect=False` during startup and restoring it once connected

## 2026-06-07
- feat(plugins): support source-specific plugin configurations (e.g. separate whitelist, blacklist, filter, replace, caption, etc.) per connection/source block in `tgcf.config.json`
- feat(config): automatically fetch and update Telegram channel names (`source_name`, `dest_names`) in `tgcf.config.json` for easier management
- feat(past): implement persistent access cache (`tgcf.access.json`) to skip re-checking accounts that lack access to specific channels, significantly speeding up startup
- feat(past): add `--clear-cache` flag to manually reset the access cache when needed
- feat(config): pretty-print and format configuration JSON file (using indent=4) when writing to disk to prevent messy output
- feat(logging): implement automatic log rotation for `tgcf.log` with a 10MB size limit and a retention of up to 3 backup logs to prevent running out of disk space

## 2026-05-14
- build: bump version to 2.0.0 (Major Release)
- build: switch to `uv` for environment management and installation
- fix(deps): resolve `pillow` version conflict with `streamlit`
- chore(gitignore): update with modern Python and `uv` patterns

## 2026-04-30
- feat(past): implement native batch forwarding (up to 100 msgs/call) when no modifying plugins are active to drastically reduce rate limits
- feat(utils): add `is_batching_safe` helper to detect modifying plugins dynamically
- feat(config): make `batch_size` fully configurable in `tgcf.config.json` (defaults to 25, tested stable up to 96)

## 2026-04-26
- refactor(config): read login secrets from `.env` automatically if empty in `tgcf.config.json` (better security)
- feat(past): implement smart channel sorting based on account access to maximize throughput
- feat(past): verify alternate account access to source channel upfront
- feat(past): add multiple session support (`ALT_SESSION_STRINGS`) to rotate accounts automatically and bypass `FloodWait` restrictions
- fix(past): fetch messages using the active alternate account to ensure media file references are valid for that session

## 2026-04-25
- fix(past): fix `--resilient` mode — now uses `connection_retries=-1` so Telethon retries forever internally; the previous approach using a Python try/except loop failed because Telethon raises `ConnectionError` in a shielded background future that couldn't be caught

## 2026-04-24
- feat(past): add `--resilient` / `-r` flag for automatic reconnect and resume on network failure
- feat(past): retry same message after FloodWait instead of skipping it
- feat(past): show direct Telegram message link in FloodWait warning log
- feat(past): print finished channel summary and unavailable channel list at end of run

## 2026-04-22
- fix(logs): show real Telegram channel name and config name in start/finish logs; fallback to config name for inaccessible channels
- fix(past): gracefully skip unavailable source channels and report them in a summary at the end
- fix(live): add null safety guards for missing `dest` and unbound `r_event_uid`
- fix(bot/utils): fix invalid escape sequence `"\."` → `r"\."`
- fix(config): replace deprecated `logging.warn` with `logging.warning`; fix trailing whitespace
- fix(plugins): remove unused `Enum` import; fix `== False` comparison
- build: add `setup.py` to support editable installs (`pip install -e .`)
- docs: add Graceful Channel Handling section to features list

## 2026-02-09
- Update README with GitHub Actions instructions
- Initial commit: Customized tgcf with bug fixes and improved error handling
