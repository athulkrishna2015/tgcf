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

    try:
        for i, client in enumerate(clients):
            await client.start()
            if i > 0:
                logging.info(f"Alternate account {i} connected successfully.")
                
        config.from_to = await config.load_from_to(primary_client, config.CONFIG.forwards)
        client = primary_client
        unavailable_channels = []
        finished_channels = []
        for from_to, forward in zip(config.from_to.items(), config.CONFIG.forwards):
            src, dest = from_to
            last_id = 0
            forward: config.Forward
            try:
                src_entity = await client.get_entity(src)
                real_name = getattr(src_entity, 'title', getattr(src_entity, 'username', str(src)))
            except Exception:
                real_name = str(src)
            con_name = forward.con_name if forward.con_name else "Unnamed"
            logging.info(f"Forwarding messages from {src} (Real Name: {real_name}, Config: {con_name}) to {dest}")
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
                            # 1. Determine active client
                            now = time.time()
                            available_idx = -1
                            for i, ban_time in enumerate(flood_until):
                                if now >= ban_time:
                                    available_idx = i
                                    break
                                    
                            if available_idx == -1:
                                # All clients are flooded. Sleep until the earliest one expires.
                                earliest = min(flood_until)
                                wait_time = earliest - now
                                logging.warning(f"All accounts are in FloodWait. Sleeping for {wait_time:.0f}s")
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
                                    logging.warning(f"Account {active_client_idx} cannot access message {message.id} in {src}. Skipping account for 5 mins.")
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
                            
                            if active_client_idx > 0:
                                logging.info(f"forwarding message with id = {last_id} (using account {active_client_idx})")
                            else:
                                logging.info(f"forwarding message with id = {last_id}")
                                
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
                            channel_id = str(src).replace("-100", "")
                            msg_link = f"https://t.me/c/{channel_id}/{message.id}"
                            logging.warning(
                                f"Account {active_client_idx} hit FloodWait: sleeping for {fwe.seconds}s before retrying — {msg_link}"
                            )
                            flood_until[active_client_idx] = time.time() + fwe.seconds
                            # Loop continues to retry with the next available account

                        except Exception as err:
                            logging.exception(err)
                            break  # skip on unknown error
                finished_channels.append(f"{src} ({real_name} / {con_name})")
                logging.info(f"Finished forwarding messages from {src} (Real Name: {real_name}, Config: {con_name})")
            except ValueError as err:
                name = forward.con_name if forward.con_name else str(src)
                logging.error(f"Could not access source {src} ({name}): {err}")
                unavailable_channels.append(f"{src} ({name})")
                continue
                
        if finished_channels:
            logging.info("=== Past mode complete. Channels processed: ===")
            for ch in finished_channels:
                logging.info(f"  ✓ {ch}")
        if unavailable_channels:
            logging.error("=== Unavailable channels (could not access): ===")
            for ch in unavailable_channels:
                logging.error(f"  ✗ {ch}")