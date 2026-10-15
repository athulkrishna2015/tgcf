"""Read-only dry run: verify Telegram login, channel access, and pending counts.

- Never forwards, never sends, never writes tgcf.config.json.
- Offsets are only read (to compute pending ~= newest - offset).

Usage:
    .venv/bin/python dryrun.py
"""
import asyncio
import sys

from telethon import TelegramClient
from telethon.sessions import StringSession

from tgcf.config import CONFIG, get_SESSION


async def resolve(clients, ident):
    """Resolve `ident` using the first account that can see it.

    Access is per-account: a channel can be invisible to the primary session
    while a secondary session resolves it fine. tgcf rotates across accounts,
    so anything reachable by *any* session is reachable in production.
    """
    last_err = None
    for idx, client in enumerate(clients):
        try:
            return await client.get_entity(ident), idx
        except Exception as err:  # noqa: BLE001
            last_err = err
    raise last_err


async def main() -> int:
    session = get_SESSION()
    clients = [TelegramClient(session, CONFIG.login.API_ID, CONFIG.login.API_HASH,
                              connection_retries=2, retry_delay=2, auto_reconnect=False)]
    for alt in getattr(CONFIG.login, "ALT_SESSION_STRINGS", []) or []:
        if alt.strip():
            clients.append(TelegramClient(StringSession(alt.strip()),
                                          CONFIG.login.API_ID, CONFIG.login.API_HASH,
                                          connection_retries=2, retry_delay=2,
                                          auto_reconnect=False))
    names = []
    for i, c in enumerate(clients):
        await c.start()
        me = await c.get_me()
        names.append(f"acct{i}(@{me.username})")
        print(f"account {i}: connected as {me.first_name} (@{me.username})")

    ok, fail = 0, 0
    for fwd in CONFIG.forwards:
        if not getattr(fwd, "use_this", True):
            continue
        try:
            src_ent, src_acct = await resolve(clients, fwd.source)
            latest = await clients[src_acct].get_messages(src_ent, limit=1)
            newest = latest[0].id if latest else 0
            pending = max(0, newest - (fwd.offset or 0))
            dests_ok = []
            for d in fwd.dest:
                try:
                    await resolve(clients, d)
                    dests_ok.append(True)
                except Exception as e:  # noqa: BLE001
                    dests_ok.append(f"DEST-FAIL {d}: {type(e).__name__}")
            name = getattr(src_ent, "title", str(fwd.source))
            via = "" if src_acct == 0 else f" via {names[src_acct]}"
            print(f"OK src={fwd.source} ({name}){via} offset={fwd.offset} "
                  f"newest={newest} pending~{pending} dests={dests_ok}")
            ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"FAIL src={fwd.source}: {type(e).__name__}: {e}")
            fail += 1

    for c in clients:
        await c.disconnect()
    print(f"dry-run done: {ok} reachable, {fail} unreachable. "
          "No messages forwarded, config untouched.")
    return 0 if fail == 0 else 1


sys.exit(asyncio.run(main()))
