"""The module for running tgcf in past mode.

- past mode can only operate with a user account.
- past mode deals with all existing messages.
"""

import asyncio
import logging
import os
import time

from telethon import TelegramClient
from telethon.errors.rpcerrorlist import ChatForwardsRestrictedError, FloodWaitError
from telethon.tl.custom.message import Message
from telethon.tl.patched import MessageService

from rich.progress import Progress, TextColumn, SpinnerColumn, TimeElapsedColumn
from tgcf import config
from tgcf import storage as st
from tgcf.config import CONFIG, get_SESSION, write_config
from tgcf.plugins import apply_plugins
from tgcf.utils import clean_session_files, send_message, is_batching_safe, get_proxy_config, update_proxies_from_channel


NETWORK_RETRY_DELAY = 30  # seconds to wait before retrying after a network error


async def forward_job(resilient: bool = False, clear_cache: bool = False) -> None:
    """Forward all existing messages in the concerned chats.

    Args:
        resilient: If True, Telethon will retry connecting forever on network errors
                   instead of giving up after 5 attempts. Progress is preserved via
                   saved offsets, so it always resumes from the last forwarded message.
        clear_cache: If True, deletes the access cache file before starting.
    """
    clean_session_files()
    if clear_cache:
        if os.path.exists(config.ACCESS_CACHE_FILE):
            os.remove(config.ACCESS_CACHE_FILE)
            logging.info("Access cache cleared.")

    if CONFIG.login.user_type != 1:
        logging.warning(
            "You cannot use bot account for tgcf past mode. Telegram does not allow bots to access chat history."
        )
        return
    SESSION = get_SESSION()
    await _run_forward_job(SESSION, resilient=resilient, clear_cache=clear_cache)


async def _run_forward_job(SESSION, resilient: bool = False, clear_cache: bool = False) -> None:
    """Core forwarding logic — runs one full pass through all channels."""
    from telethon.sessions import StringSession
    # connection_retries=-1 means Telethon retries forever (used in resilient mode)
    actual_retries = -1 if resilient else 5
    if resilient:
        logging.info(
            "Resilient mode ON: will retry connecting indefinitely if network drops."
        )
        
    clients = []
    flood_until = []
    client_names = []
    client_user_ids = []
    primary_client = None

    max_retries = 10
    for attempt in range(max_retries):
        clients = []
        flood_until = []
        
        proxy_config = get_proxy_config()
        primary_client = TelegramClient(
            SESSION, CONFIG.login.API_ID, CONFIG.login.API_HASH,
            connection_retries=2,
            retry_delay=2,
            auto_reconnect=False,
            **proxy_config
        )
        clients.append(primary_client)
        flood_until.append(0.0)
        
        for idx, alt_session in enumerate(CONFIG.login.ALT_SESSION_STRINGS):
            if alt_session.strip():
                alt_client = TelegramClient(
                    StringSession(alt_session.strip()), CONFIG.login.API_ID, CONFIG.login.API_HASH,
                    connection_retries=2,
                    retry_delay=2,
                    auto_reconnect=False,
                    **proxy_config
                )
                clients.append(alt_client)
                flood_until.append(0.0)
                logging.info(f"Loaded alternate session {idx + 1}")

        client_names = [None] * len(clients)
        client_user_ids = [None] * len(clients)

        async def start_client(i, client):
            await client.start()
            me = await client.get_me()
            client_user_ids[i] = me.id
            name = getattr(me, "first_name", "")
            if getattr(me, "last_name", ""):
                name += f" {me.last_name}"
            if getattr(me, "username", ""):
                name += f" (@{me.username})"
            if not name:
                name = getattr(me, "phone", f"Account {i}")
            client_names[i] = name

            if i > 0:
                logging.info(f"Alternate account {i} ({name}) connected successfully.")
            else:
                logging.info(f"Primary account ({name}) connected successfully.")

        try:
            await asyncio.gather(*(start_client(i, client) for i, client in enumerate(clients)))
            # Set the actual connection retries for the rest of the execution
            for c in clients:
                c._connection_retries = actual_retries
                c._retry_delay = 30
                c._auto_reconnect = True
            asyncio.create_task(update_proxies_from_channel(primary_client))
            break  # Success!
        except Exception as e:
            logging.warning(f"Connection attempt {attempt + 1} failed: {e}")
            from tgcf.utils import invalidate_proxy
            invalidate_proxy()
            for c in clients:
                try:
                    await c.disconnect()
                except Exception:
                    pass
            if attempt == max_retries - 1:
                logging.error("Failed to connect after all proxy retries.")
                raise e
            logging.info("Retrying with a different proxy...")

    config.from_to = await config.load_from_to(primary_client, config.CONFIG.forwards)
    client = primary_client
    unavailable_channels = []
    finished_channels = []
    # Minimal upfront info for sorting (Names and TTL for Primary Account only)
    logging.info("Fetching minimal channel info for sorting...")
    access_cache = config.read_access_cache()
    channel_data_list = []

    async def get_basic_info(from_to, forward):
        src, dest = from_to
        has_ttl = False
        try:
            src_entity = await primary_client.get_entity(src)
            has_ttl = bool(getattr(src_entity, "ttl_period", 0))
        except Exception:
            pass
        return {
            "src": src,
            "dest": dest,
            "forward": forward,
            "real_name": forward.source_name,
            "con_name": forward.con_name if forward.con_name else "Unnamed",
            "has_ttl": has_ttl,
        }

    active_forwards = [f for f in config.CONFIG.forwards if f.use_this]
    results = await asyncio.gather(
        *(
            get_basic_info(ft, f)
            for ft, f in zip(config.from_to.items(), active_forwards)
        )
    )
    channel_data_list = list(results)

    # Sort channels by presence of delete timer (TTL) first
    channel_data_list.sort(key=lambda x: not x["has_ttl"])

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.fields[channel]}[/bold blue]"),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
        ) as progress:
            for data in channel_data_list:
                src = data["src"]
                dest = data["dest"]
                forward = data["forward"]
                real_name = data["real_name"]
                con_name = data["con_name"]

                # Lazy Client Selection
                client = None
                active_client_idx = -1
                allowed_clients = []

                for i in range(len(clients)):
                    uid = client_user_ids[i]
                    if str(src) in access_cache and uid in access_cache[str(src)]:
                        continue

                    try:
                        await clients[i].get_entity(src)
                        for d in dest:
                            await clients[i].get_entity(d)
                        
                        # Found a working client!
                        allowed_clients.append(i)
                        client = clients[i]
                        active_client_idx = i
                        
                        # STOP SEARCHING: If the primary (or first available) account works, we are done.
                        break 
                    except Exception as e:
                        if str(src) not in access_cache:
                            access_cache[str(src)] = []
                        if uid not in access_cache[str(src)]:
                            access_cache[str(src)].append(uid)
                        logging.warning(f"  Account {i} ({client_names[i]}) cannot access {real_name}: {e}")
                
                if not allowed_clients:
                    name = con_name if con_name else str(src)
                    logging.error(f"Could not process connection {name} (source={src}): No accounts have access.")
                    unavailable_channels.append(f"{src} ({name})")
                    continue

                if active_client_idx == -1:
                    # All allowed clients are in FloodWait
                    active_client_idx = allowed_clients[0]
                    client = clients[active_client_idx]

                last_id = 0
                stripped_id = str(src).replace("-100", "")
                task_id = progress.add_task(
                    "Connecting...",
                    channel=f"{real_name[:20]:<20}",
                )
                
                try:

                    batch_safe = is_batching_safe(forward.plugins)
                    batch = []
                    
                    async def flush_batch():
                        nonlocal batch, last_id
                        if not batch: return
                        
                        while True:
                            try:
                                now = time.time()
                                available_idx = -1
                                for i in allowed_clients:
                                    if now >= flood_until[i]:
                                        available_idx = i
                                        break
                                        
                                if available_idx == -1:
                                    earliest = min([flood_until[i] for i in allowed_clients])
                                    wait_time = earliest - now
                                    for remaining in range(int(wait_time), 0, -1):
                                        progress.update(task_id, description=f"[bold yellow]FloodWait: all accounts banned. Resuming in {remaining}s[/bold yellow]")
                                        time.sleep(1)
                                    continue
                                    
                                active_client_idx = available_idx
                                active_client = clients[active_client_idx]
                                
                                for d in dest:
                                    fwded_msgs = await active_client.forward_messages(
                                        d, 
                                        [m.id for m in batch], 
                                        src, 
                                        drop_author=not CONFIG.show_forwarded_from
                                    )
                                    
                                    # Update st.stored for all messages in batch
                                    for i, m in enumerate(batch):
                                        event = st.DummyEvent(m.chat_id, m.id)
                                        event_uid = st.EventUid(event)
                                        if event_uid not in st.stored:
                                            st.stored[event_uid] = {}
                                        if fwded_msgs and i < len(fwded_msgs) and fwded_msgs[i]:
                                            st.stored[event_uid].update({d: fwded_msgs[i].id})
                                            
                                last_id = batch[-1].id
                                msg_link = f"https://t.me/c/{stripped_id}/{last_id}"
                                account_name = client_names[active_client_idx]
                                progress.update(
                                    task_id, 
                                    description=f"Batch: [cyan]{last_id}[/cyan] ({len(batch)} msgs) [dim]({account_name})[/dim] - [blue]{msg_link}[/blue]"
                                )
                                
                                forward.offset = last_id
                                write_config(CONFIG, persist=False)
                                time.sleep(CONFIG.past.delay)
                                batch.clear()
                                break
                            except ChatForwardsRestrictedError:
                                logging.warning(f"Skipping batch ending in {batch[-1].id}: chat is protected.")
                                last_id = batch[-1].id
                                forward.offset = last_id
                                write_config(CONFIG, persist=False)
                                batch.clear()
                                break
                            except FloodWaitError as fwe:
                                logging.warning(f"Account {active_client_idx} hit FloodWait: sleeping for {fwe.seconds}s before retrying")
                                flood_until[active_client_idx] = time.time() + fwe.seconds
                            except Exception as err:
                                logging.warning(f"Batch forward failed, falling back to one-by-one. Error: {err}")
                                # Fallback one by one
                                for m in batch:
                                    await process_one(m)
                                batch.clear()
                                break
                                
                    async def process_one(message):
                        nonlocal last_id
                        event = st.DummyEvent(message.chat_id, message.id)
                        event_uid = st.EventUid(event)

                        r_event_uid = None
                        while True:
                            try:
                                # 1. Determine active client from ALLOWED clients
                                now = time.time()
                                available_idx = -1
                                for i in allowed_clients:
                                    if now >= flood_until[i]:
                                        available_idx = i
                                        break
                                        
                                if available_idx == -1:
                                    # All ALLOWED clients are flooded. Sleep until the earliest one expires.
                                    earliest = min([flood_until[i] for i in allowed_clients])
                                    wait_time = earliest - now
                                    for remaining in range(int(wait_time), 0, -1):
                                        progress.update(task_id, description=f"[bold yellow]FloodWait: all accounts banned. Resuming in {remaining}s[/bold yellow]")
                                        time.sleep(1)
                                    continue
                                    
                                active_client_idx = available_idx
                                active_client = clients[active_client_idx]
                                
                                # 2. Get message object for active client
                                if active_client_idx == 0:
                                    active_message = message
                                else:
                                    active_message_list = await active_client.get_messages(src, ids=[message.id])
                                    if not active_message_list or not active_message_list[0]:
                                        progress.update(task_id, description=f"[bold red]Account {active_client_idx} failed to fetch {message.id}[/bold red]")
                                        flood_until[active_client_idx] = now + 300
                                        continue
                                    active_message = active_message_list[0]
                                    
                                # 3. Apply plugins
                                tm = await apply_plugins(active_message)
                                if not tm:
                                    break
                                st.stored[event_uid] = {}

                                if message.is_reply:
                                    r_event = st.DummyEvent(
                                        message.chat_id, message.reply_to_msg_id
                                    )
                                    r_event_uid = st.EventUid(r_event)
                                for d in dest:
                                    if message.is_reply and r_event_uid in st.stored:
                                        tm.reply_to = st.stored.get(r_event_uid).get(d)
                                    fwded_msg = await send_message(d, tm)
                                    st.stored[event_uid].update({d: fwded_msg.id})
                                tm.clear()
                                last_id = message.id
                                
                                msg_link = f"https://t.me/c/{stripped_id}/{last_id}"
                                account_name = client_names[active_client_idx]
                                progress.update(
                                    task_id, 
                                    description=f"Msg: [cyan]{last_id}[/cyan] [dim]({account_name})[/dim] - [blue]{msg_link}[/blue]"
                                )
                                
                                forward.offset = last_id
                                write_config(CONFIG, persist=False)
                                time.sleep(CONFIG.past.delay)
                                break  # success

                            except ChatForwardsRestrictedError:
                                logging.warning(
                                    f"Skipping message {message.id} in {src}: chat is protected."
                                )
                                last_id = message.id
                                forward.offset = last_id
                                write_config(CONFIG, persist=False)
                                break  # skip this message

                            except FloodWaitError as fwe:
                                msg_link = f"https://t.me/c/{stripped_id}/{message.id}"
                                logging.warning(
                                    f"Account {active_client_idx} hit FloodWait: sleeping for {fwe.seconds}s before retrying — {msg_link}"
                                )
                                flood_until[active_client_idx] = time.time() + fwe.seconds
                                # Loop continues to retry with the next available account

                            except Exception as err:
                                logging.exception(err)
                                raise err

                    async for message in client.iter_messages(
                        src, reverse=True, offset_id=forward.offset
                    ):
                        message: Message

                        if forward.end and last_id > forward.end:
                            continue
                        if isinstance(message, MessageService):
                            continue
                            
                        if batch_safe:
                            tm = await apply_plugins(message)
                            if not tm:
                                continue
                            batch.append(message)
                            if len(batch) >= CONFIG.past.batch_size:
                                await flush_batch()
                        else:
                            await process_one(message)
                            
                    if batch_safe and batch:
                        await flush_batch()

                    finished_channels.append(f"{src} ({real_name} / {con_name})")
                    progress.update(task_id, description="[bold green]Finished[/bold green]", visible=False)
                except Exception as err:
                    name = forward.con_name if forward.con_name else str(src)
                    logging.error(f"Could not process connection {name} (source={src}): {err}")
                    unavailable_channels.append(f"{src} ({name})")
                    progress.update(task_id, description="[bold red]Failed[/bold red]", visible=False)
                    continue
    
        if finished_channels:
            logging.info("=== Past mode complete. Channels processed: ===")
            for ch in finished_channels:
                logging.info(f"  ✓ {ch}")
        if unavailable_channels:
            logging.error("=== Unavailable channels (could not access): ===")
            for ch in unavailable_channels:
                logging.error(f"  ✗ {ch}")
    finally:
        for client in clients:
            await client.disconnect()