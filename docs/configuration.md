# Configuration & Variables Reference

## Environment Variables
These variables can be defined in your `.env` file:
- `API_ID`: Your Telegram API ID.
- `API_HASH`: Your Telegram API Hash.
- `SESSION_STRING`: Your main Telegram user or bot session string.
- `SESSION_STRING_2` to `SESSION_STRING_20`: (Optional) Alternate sessions for account rotation on FloodWait.
- `BOT_TOKEN`: Your Telegram Bot token (required if logging in as a bot).
- `PASSWORD`: Password to restrict access to the Web UI (defaults to `tgcf`).
- `MONGO_CON_STR`: Connection string for MongoDB (used for online config storage).
- `MONGO_DB_NAME`: MongoDB database name (defaults to `tgcf-config`).
- `MONGO_COL_NAME`: MongoDB collection name (defaults to `tgcf-instance-0`).
- `TGCF_PROXY_TYPE`: (Optional) Proxy type to bypass network bans/restrictions (`socks5`, `socks4`, `http`, or `mtproto`). Defaults to `socks5`.
- `TGCF_PROXY_HOST`: (Optional) Proxy server host (e.g. `127.0.0.1` or `proxy.example.com`).
- `TGCF_PROXY_PORT`: (Optional) Proxy server port (e.g. `1080` or `8080`).
- `TGCF_PROXY_USER`: (Optional) Proxy username (for SOCKS5/SOCKS4/HTTP).
- `TGCF_PROXY_PASSWORD` / `TGCF_PROXY_PASS`: (Optional) Proxy password (for SOCKS5/SOCKS4/HTTP).
- `TGCF_PROXY_SECRET`: (Optional) Proxy secret key (hex-encoded string, required for `mtproto`).
- `TGCF_PROXY_CHECK_TIMEOUT`: (Optional) Socket check timeout in seconds to verify if a proxy is alive (defaults to `1.5`).
- `TGCF_DIRECT_CHECK_TIMEOUT`: (Optional) Timeout in seconds to verify direct connection to Telegram before attempting proxy fallback (defaults to `2.0`).

## Available File Types for Filtering
When configuring whitelist/blacklist in the `"files"` filter plugin, use these values:
- `document`: All document attachments (PDFs, ZIPs, APKs, etc.).
- `photo`: Images/Photos.
- `video`: Videos.
- `video_note`: Round video notes.
- `audio`: Audio recordings/voice notes.
- `sticker`: Telegram stickers.
- `gif`: Animated GIFs.
- `contact`: Contact cards.
- `nofile`: Text-only posts containing no files or attachments.

## Available Style Styles for Format Plugin
When using the `"fmt"` (Format) plugin:
- `bold`, `italics`, `code` (monospace), `strike` (strikethrough), `plain` (strip formatting), `preserve` (keep original formatting).
