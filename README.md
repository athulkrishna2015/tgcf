# tgcf - Telegram Control Foundation

A customized version of `tgcf` for automated telegram message forwarding.

## Features
- Forward messages from past history or live.
- Filter messages based on text, users, or file types.
- Supports protected chats (gracefully skips restricted content).
- Robust ID handling for different Telegram peer formats.

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
   - Copy `.env.example` to `.env` and add your credentials.
   - Create a `tgcf.config.json` with your forwarding rules.

## Usage
Run in past mode:
```bash
tgcf past
```

Run in live mode:
```bash
tgcf live
```
