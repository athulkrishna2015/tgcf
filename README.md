# tgcf - Telegram Control Foundation

A customized version of `tgcf` for automated telegram message forwarding.

## Features
- Forward messages from past history or live.
- Filter messages based on text, users, or file types.
- Supports protected chats (gracefully skips restricted content).
- Gracefully handles unavailable or missing source channels by skipping them and reporting errors at the end.
- Robust ID handling for different Telegram peer formats.
- **Resilient mode**: automatically reconnects and resumes after network outages (`tgcf past --resilient`).
- **Multiple Sessions**: configure alternate accounts to bypass `FloodWait` limits.
- **Smart Channel Sorting**: automatically prioritizes processing highly-restricted channels first to maximize account availability before rate limits hit.
- **Native Batch Forwarding**: automatically groups up to 100 messages per API call if no modifying plugins are active, drastically reducing rate limits.
- Detailed logging: shows real Telegram channel names, message links for FloodWait retries, and a full summary on completion.

## Setup

1. **Clone the repository**
2. **Setup environment and install dependencies using [uv](https://github.com/astral-sh/uv):**
   ```bash
   # Create venv and install in editable mode
   uv venv --python 3.11
   source .venv/bin/activate
   uv pip install -e .
   ```
3. **Configure:**
   - Copy `.env.example` to `.env` and add your credentials (`API_ID`, `API_HASH`, `SESSION_STRING`).
   - Create a `tgcf.config.json` with your forwarding rules. Keep the `"login": {}` block empty to automatically load secrets from `.env`.
   - **(Optional) Alternate Accounts**: To bypass `FloodWait` limits, you can configure alternate user sessions in your `.env` file using numbered variables (`SESSION_STRING_2`, `SESSION_STRING_3`, etc. up to `20`). These accounts will automatically take over when the primary hits a rate limit. **Note: Alternate accounts must have joined the source channels.**
     ```bash
     # Inside your .env file
     SESSION_STRING=your_main_session
     SESSION_STRING_2=alternate_session_1
     SESSION_STRING_3=alternate_session_2
     ```

## Usage
Run in past mode:
```bash
tgcf past
```

By default, past mode will batch forward 25 messages at once (if no modifying plugins are active) to drastically speed up forwarding. You can customize this threshold in your `tgcf.config.json` by adding `batch_size` (up to 100) inside the `past` block.

Run in past mode with automatic network recovery:
```bash
tgcf past --resilient
# or
tgcf past -r
```
If the connection drops, tgcf will wait 30 seconds and reconnect automatically.
Progress is saved to disk, so it always resumes from the last forwarded message.

Run in live mode:
```bash
tgcf live
```

## Running on GitHub Actions

This repository includes a GitHub Actions workflow to run `tgcf past` every hour.

### Configuration
To use it, add the following **Secrets** to your GitHub repository:
- `API_ID`: Your Telegram API ID.
- `API_HASH`: Your Telegram API Hash.
- `SESSION_STRING`: Your Telegram Session String.
- `TGCF_CONFIG_JSON`: The full content of your `tgcf.config.json`.

### Note on Persistence
GitHub Actions does not save changes to the `tgcf.config.json` file across runs. If you need to keep track of the message `offset`, consider using the **MongoDB** integration by setting the `MONGO_CON_STR` environment variable.

## Changelog

### 2026-05-14
- build: bump version to 2.0.0 (Major Release)
- build: switch to `uv` for environment management and installation
- fix(deps): resolve `pillow` version conflict with `streamlit`
- chore(gitignore): update with modern Python and `uv` patterns

### 2026-04-30
- feat(past): implement native batch forwarding (up to 100 msgs/call) when no modifying plugins are active to drastically reduce rate limits
- feat(utils): add `is_batching_safe` helper to detect modifying plugins dynamically
- feat(config): make `batch_size` fully configurable in `tgcf.config.json` (defaults to 25, tested stable up to 96)

### 2026-04-26
- refactor(config): read login secrets from `.env` automatically if empty in `tgcf.config.json` (better security)
- feat(past): implement smart channel sorting based on account access to maximize throughput
- feat(past): verify alternate account access to source channel upfront
- feat(past): add multiple session support (`ALT_SESSION_STRINGS`) to rotate accounts automatically and bypass `FloodWait` restrictions
- fix(past): fetch messages using the active alternate account to ensure media file references are valid for that session

### 2026-04-25
- fix(past): fix `--resilient` mode — now uses `connection_retries=-1` so Telethon retries forever internally; the previous approach using a Python try/except loop failed because Telethon raises `ConnectionError` in a shielded background future that couldn't be caught

### 2026-04-24
- feat(past): add `--resilient` / `-r` flag for automatic reconnect and resume on network failure
- feat(past): retry same message after FloodWait instead of skipping it
- feat(past): show direct Telegram message link in FloodWait warning log
- feat(past): print finished channel summary and unavailable channel list at end of run

### 2026-04-22
- fix(logs): show real Telegram channel name and config name in start/finish logs; fallback to config name for inaccessible channels
- fix(past): gracefully skip unavailable source channels and report them in a summary at the end
- fix(live): add null safety guards for missing `dest` and unbound `r_event_uid`
- fix(bot/utils): fix invalid escape sequence `"\."` → `r"\."`
- fix(config): replace deprecated `logging.warn` with `logging.warning`; fix trailing whitespace
- fix(plugins): remove unused `Enum` import; fix `== False` comparison
- build: add `setup.py` to support editable installs (`pip install -e .`)
- docs: add Graceful Channel Handling section to features list

### 2026-02-09
- Update README with GitHub Actions instructions
- Initial commit: Customized tgcf with bug fixes and improved error handling