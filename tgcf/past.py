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
        resilient: If True, automatically retry on network errors instead of crashing.
                   Progress is preserved via saved offsets, so it resumes from last point.
    """
    clean_session_files()
    if CONFIG.login.user_type != 1:
        logging.warning(
            "You cannot use bot account for tgcf past mode. Telegram does not allow bots to access chat history."
        )
        return
    SESSION = get_SESSION()

    attempt = 0
    while True:
        attempt += 1
        try:
            await _run_forward_job(SESSION)
            break  # completed successfully
        except (ConnectionError, OSError) as err:
            if not resilient:
                raise
            logging.error(
                f"Network error on attempt {attempt}: {err}\n"
                f"Retrying in {NETWORK_RETRY_DELAY}s... (progress is saved, will resume from last offset)"
            )
            await asyncio.sleep(NETWORK_RETRY_DELAY)
        except Exception as err:
            raise  # non-network errors always propagate


async def _run_forward_job(SESSION) -> None:
    """Core forwarding logic — runs one full pass through all channels."""
    async with TelegramClient(
        SESSION, CONFIG.login.API_ID, CONFIG.login.API_HASH
    ) as client:
        config.from_to = await config.load_from_to(client, config.CONFIG.forwards)
        client: TelegramClient
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
                    while True:
                        try:
                            tm = await apply_plugins(message)
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
                            logging.info(f"forwarding message with id = {last_id}")
                            forward.offset = last_id
                            write_config(CONFIG, persist=False)
                            time.sleep(CONFIG.past.delay)
                            logging.info(f"slept for {CONFIG.past.delay} seconds")
                            break  # success, move to next message

                        except ChatForwardsRestrictedError:
                            logging.warning(
                                f"Skipping message {message.id} in {src}: chat is protected."
                            )
                            last_id = message.id
                            forward.offset = last_id
                            write_config(CONFIG, persist=False)
                            break  # skip this message
                        except FloodWaitError as fwe:
                            # Build a direct Telegram link to the message
                            # Private supergroup IDs are like -100XXXXXXXXX; strip the -100 prefix
                            channel_id = str(src).replace("-100", "")
                            msg_link = f"https://t.me/c/{channel_id}/{message.id}"
                            logging.warning(
                                f"FloodWait: sleeping for {fwe.seconds}s before retrying — {msg_link}"
                            )
                            await asyncio.sleep(delay=fwe.seconds)
                            # loop continues — retries the same message
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