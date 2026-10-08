# Scheduled Execution

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

## Cron

To run `tgcf` periodically on a Linux server (e.g., every 2 hours), you can configure a cron job.

### Setup

Open your crontab configuration editor:
```bash
crontab -e
```

Add the following entries (adjust paths to match your actual setup) to schedule it on boot, trigger it on system wake (via DBus signal monitoring), and run every 2 hours:
```cron
# Run at boot, exit if another run is already active
@reboot cd /mnt/0946E88701BE265B/portable/tgcf/who && flock -n tgcf.lock .venv/bin/tgcf past --resilient --loud >> cron.log 2>&1

# Start the background wake-from-sleep listener daemon on boot
@reboot cd /mnt/0946E88701BE265B/portable/tgcf/who && ./tgcf_wake_listener.sh >> cron.log 2>&1 &

# Run every 2 hours, exit if another run is already active
0 */2 * * * cd /mnt/0946E88701BE265B/portable/tgcf/who && flock -n tgcf.lock .venv/bin/tgcf past --resilient --loud >> cron.log 2>&1
```

### Logging
- `cron.log`: Appends standard output, stderr, and cron/shell startup errors (like interpreter problems or path issues).
- `tgcf.log`: Native Python application logs (includes execution summaries and filter statuses).

### Troubleshooting NTFS Mounts (Windows/Linux dual-boot)
If this repository is located on a dual-boot NTFS partition, symlinks inside `.venv/bin/` (e.g., `python`, `python3`) created under Windows/WSL might show up in Linux as `unsupported reparse tag 0xa000000c`.

This will prevent cron/bash from running the wrapper scripts and throw:
```
bash: .venv/bin/tgcf: ...: bad interpreter: No such file or directory
```

To resolve this issue, recreate the virtualenv natively under Linux:
```bash
mv .venv .venv.bak
uv venv --python 3.11 --prompt who
uv pip install -r requirements.txt
uv pip install --no-deps -e .
```

Or, for a quick repair, replace the broken stubs with real copies of the
pinned interpreter (see `pyvenv.cfg` for the version):
```bash
# Recreate symlinks (e.g. pointing to /usr/bin/python3 or local uv installation)
rm -f .venv/bin/python .venv/bin/python3 .venv/bin/python3.11
ln -s /home/admin/.local/share/uv/python/cpython-3.11-linux-x86_64-gnu/bin/python3.11 .venv/bin/python
ln -s python .venv/bin/python3
ln -s python .venv/bin/python3.11
```

> Note: `uv pip install` never touches `.venv/bin/python*` — only `uv venv`
> (re)creation does. Always (re)create this venv from Linux, not Windows.
