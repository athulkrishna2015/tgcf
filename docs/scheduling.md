# Scheduled Execution

## Running on GitHub Actions

`tgcf past` runs on a schedule on GitHub Actions. Because the workflow must
record which messages it has already forwarded, it commits an updated offset
back after every run. To keep this repository's `main` clean, the workflow and
the mutable config live in a **separate private repository**:

| Repository | Contents |
|---|---|
| `athulkrishna2015/tgcf` (this one, public) | Source code only. No workflow, no config. |
| `athulkrishna2015/tgcf-runner` (private) | The workflow, `tgcf.config.json`, and the credentials. |

Each run checks this repository out into `app/`, copies the config in, runs
`tgcf past`, then commits the advanced offsets back to the runner repo. Source
changes here take effect on the next run — there is no sync step.

### Configuration
Add these **Secrets** to `tgcf-runner` (not to this repository):

- `API_ID`: Your Telegram API ID.
- `API_HASH`: Your Telegram API Hash.
- `SESSION_STRING`: Your primary user session string.
- `SESSION_STRING_2`, `SESSION_STRING_3`: Alternate accounts.

`SESSION_STRING_2` and `_3` are not optional. `tgcf` rotates across accounts when
it hits a flood wait; without them it degrades to a single account.

The config file itself is committed to the runner repo and carries no
credentials — `write_config_to_file()` strips the `login` block on write.

### Do not run cron at the same time
The cron setup below and the Actions workflow both advance the same offsets in
`tgcf.config.json`, independently. Running both will double-post messages or
leave gaps. If you enable Actions, comment out the crontab.

### Note on Persistence
An earlier setup kept the config in this repository as a `TGCF_CONFIG_JSON`
secret. That does not work: the workflow overwrote `tgcf.config.json` from the
static secret at the start of every run, discarding the offsets it had just
advanced, so each run re-posted everything since the last committed offset. The
runner-repo layout fixes that by making the config a file the workflow can
actually commit back to.

You can also use the **MongoDB** integration by setting the `MONGO_CON_STR`
environment variable, which stores the config in Mongo instead of a file.

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
