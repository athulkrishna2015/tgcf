"""The module for running tgcf in past mode.

- past mode can only operate with a user account.
- past mode deals with all existing messages.
"""

import asyncio
import logging
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
from tgcf.utils import clean_session_files, send_message


NETWORK_RETRY_DELAY = 30  # seconds to wait before retrying after a network error


async def forward_job(resilient: bool = False) -> None:
    """Forward all existing messages in the concerned chats.

    Args:
        resilient: If True, Telethon will retry connecting forever on network errors
                   instead of giving up after 5 attempts. Progress is preserved via
                   saved offsets, so it always resumes from the last forwarded message.
    """
    clean_session_files()
    if CONFIG.login.user_type != 1:
        logging.warning(
            "You cannot use bot account for tgcf past mode. Telegram does not allow bots to access chat history."
        )
        return
    SESSION = get_SESSION()
    await _run_forward_job(SESSION, resilient=resilient)


async def _run_forward_job(SESSION, resilient: bool = False) -> None:
    """Core forwarding logic — runs one full pass through all channels."""
    from telethon.sessions import StringSession
    # connection_retries=-1 means Telethon retries forever (used in resilient mode)
    connection_retries = -1 if resilient else 5
    if resilient:
        logging.info(
            "Resilient mode ON: will retry connecting indefinitely if network drops."
        )
        
    clients = []
    flood_until = []
    
    primary_client = TelegramClient(
        SESSION, CONFIG.login.API_ID, CONFIG.login.API_HASH,
        connection_retries=connection_retries,
        retry_delay=30,
    )
    clients.append(primary_client)
    flood_until.append(0.0)
    
    for idx, alt_session in enumerate(CONFIG.login.ALT_SESSION_STRINGS):
        if alt_session.strip():
            alt_client = TelegramClient(
                StringSession(alt_session.strip()), CONFIG.login.API_ID, CONFIG.login.API_HASH,
                connection_retries=connection_retries,
                retry_delay=30,
            )
            clients.append(alt_client)
            flood_until.append(0.0)
            logging.info(f"Loaded alternate session {idx + 1}")

        client_names = []
        for i, client in enumerate(clients):
            await client.start()
            me = await client.get_me()
            name = getattr(me, 'first_name', '')
            if getattr(me, 'last_name', ''):
                name += f" {me.last_name}"
            if getattr(me, 'username', ''):
                name += f" (@{me.username})"
            if not name:
                name = getattr(me, 'phone', f"Account {i}")
            client_names.append(name)
            
            if i > 0:
                logging.info(f"Alternate account {i} ({name}) connected successfully.")
            else:
                logging.info(f"Primary account ({name}) connected successfully.")
                
        config.from_to = await config.load_from_to(primary_client, config.CONFIG.forwards)
        client = primary_client
        unavailable_channels = []
        finished_channels = []
        # Upfront access check and smart sorting
        logging.info("Performing upfront access checks for smart channel sorting...")
        channel_access_data = []
        for from_to, forward in zip(config.from_to.items(), config.CONFIG.forwards):
            src, dest = from_to
            has_ttl = False
            try:
                src_entity = await primary_client.get_entity(src)
                real_name = getattr(src_entity, 'title', getattr(src_entity, 'username', str(src)))
                has_ttl = bool(getattr(src_entity, 'ttl_period', 0))
            except Exception:
                real_name = str(src)
            con_name = forward.con_name if forward.con_name else "Unnamed"
            
            allowed_clients = [0]  # Primary client is assumed to have access
            for i in range(1, len(clients)):
                try:
                    await clients[i].get_entity(src)
                    allowed_clients.append(i)
                except Exception:
                    pass
            
            channel_access_data.append({
                'src': src,
                'dest': dest,
                'forward': forward,
                'real_name': real_name,
                'con_name': con_name,
                'allowed_clients': allowed_clients,
                'has_ttl': has_ttl
            })
            
        # Sort channels by presence of delete timer, then number of allowed clients (ascending)
        # Channels with delete timers (TTL) are processed FIRST, then channels with fewest accounts
        channel_access_data.sort(key=lambda x: (not x['has_ttl'], len(x['allowed_clients'])))
        
        logging.info("Smart sorting complete. Processing order:")
        for i, data in enumerate(channel_access_data):
            ttl_str = "[Timer] " if data['has_ttl'] else ""
            logging.info(f"{i+1}. {ttl_str}{data['src']} - {len(data['allowed_clients'])} accounts have access")

        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.fields[channel]}[/bold blue]"),
                TextColumn("[progress.description]{task.description}"),
                TimeElapsedColumn(),
            ) as progress:
                for channel_data in channel_access_data:
                    src = channel_data['src']
                    dest = channel_data['dest']
                    forward = channel_data['forward']
                    real_name = channel_data['real_name']
                    con_name = channel_data['con_name']
                    allowed_clients = channel_data['allowed_clients']
                    last_id = 0
                    
                    stripped_id = str(src).replace("-100", "")
                    task_id = progress.add_task(
                        "Connecting...",
                        channel=f"{real_name[:20]:<20}",
                    )
                    
                    try:
                        async for message in client.iter_messages(
                            src, reverse=True, offset_id=forward.offset
                        ):
                            message: Message
                            event = st.DummyEvent(message.chat_id, message.id)
                            event_uid = st.EventUid(event)

                            if forward.end and last_id > forward.end:
                                continue
                            if isinstance(message, MessageService):
                                continue
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
                                        progress.update(task_id, description=f"[bold yellow]FloodWait: all accounts banned. Waiting {wait_time:.0f}s[/bold yellow]")
                                        time.sleep(wait_time)
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
                                    break  # skip on unknown error
                        finished_channels.append(f"{src} ({real_name} / {con_name})")
                        progress.update(task_id, description="[bold green]Finished[/bold green]", visible=False)
                    except ValueError as err:
                        name = forward.con_name if forward.con_name else str(src)
                        logging.error(f"Could not access source {src} ({name}): {err}")
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