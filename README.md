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
- Detailed logging: shows real Telegram channel names, message links for FloodWait retries, and a full summary on completion.

## Setup

1. **Clone the repository**
2. **Create a virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   pip install -e .
   ```
4. **Configure:**
   - Copy `.env.example` to `.env` and add your credentials (`API_ID`, `API_HASH`, `SESSION_STRING`).
   - Create a `tgcf.config.json` with your forwarding rules. Keep the `"login": {}` block empty to automatically load secrets from `.env`.
   - **(Optional) Alternate Accounts**: To bypass `FloodWait` limits, you can configure alternate user sessions in your `.env` file using a comma-separated list. These accounts will automatically take over when the primary hits a rate limit. **Note: Alternate accounts must have joined the source channels.**
     ```bash
     # Inside your .env file
     ALT_SESSION_STRINGS=alternate_session_1,alternate_session_2
     ```

## Usage
Run in past mode:
```bash
tgcf past
```

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