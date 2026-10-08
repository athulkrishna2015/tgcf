# Usage

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

## Dry run (read-only check)

`dryrun.py` verifies login, source/destination access, and pending message counts
without forwarding anything or touching `tgcf.config.json` offsets:
```bash
.venv/bin/python dryrun.py
```
Use it after venv/cron changes to confirm everything works. Verify offsets are
untouched with `md5sum tgcf.config.json` before and after.
