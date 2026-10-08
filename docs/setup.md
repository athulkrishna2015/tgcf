# Setup

1. **Clone the repository**
2. **Setup environment and install dependencies using [uv](https://github.com/astral-sh/uv):**
   ```bash
   # Create venv and install in editable mode
   uv venv --python 3.11
   source .venv/bin/activate
   uv pip install -e .
   ```
   > If this repo lives on a dual-boot NTFS partition, recreate `.venv` from
   > Linux so its symlinks are native (see [NTFS troubleshooting](scheduling.md#troubleshooting-ntfs-mounts-windowslinux-dual-boot)).
3. **Configure:**
   - Copy `.env.example` to `.env` and add your credentials (`API_ID`, `API_HASH`, `SESSION_STRING`).
   - Create a `tgcf.config.json` with your forwarding rules. Keep the `"login": {}` block empty to automatically load secrets from `.env`.
   - **(Optional) Source-Specific Plugins**: You can define custom `plugins` configurations for individual connections/sources directly inside their forward blocks in `tgcf.config.json`. If a connection specifies its own `plugins` configuration, it will use that local configuration. If it doesn't specify a `plugins` block, it automatically falls back to the top-level global `plugins` configuration.
   - **(Optional) Alternate Accounts**: To bypass `FloodWait` limits, you can configure alternate user sessions in your `.env` file using numbered variables (`SESSION_STRING_2`, `SESSION_STRING_3`, etc. up to `20`). These accounts will automatically take over when the primary hits a rate limit. **Note: Alternate accounts must have joined the source channels.**
     ```bash
     # Inside your .env file
     SESSION_STRING=your_main_session
     SESSION_STRING_2=alternate_session_1
     SESSION_STRING_3=alternate_session_2
     ```
