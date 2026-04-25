"""The module for running tgcf in past mode.

- past mode can only operate with a user account.
- past mode deals with all existing messages.
"""

import asyncio
import logging
import time

from telethon import TelegramClient
from telethon.errors.rpcerrorlist import ChatForwardsRestrictedError, FloodWaitError, MediaEmptyError
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
    """Core forwarding logic — runs one full pass through all channels.

    Uses a deferred queue: if a FloodWait is hit on a source, it is skipped
    and re-queued with a resume timestamp. Other sources continue processing
    in the meantime. A source is retried only after its flood wait expires.
    """
    # connection_retries=-1 means Telethon retries forever (used in resilient mode)
    connection_retries = -1 if resilient else 5
    if resilient:
        logging.info(
            "Resilient mode ON: will retry connecting indefinitely if network drops."
        )
    async with TelegramClient(
        SESSION, CONFIG.login.API_ID, CONFIG.login.API_HASH,
        connection_retries=connection_retries,
        retry_delay=30,
    ) as client:
        # Initialize helper bot if BOT_TOKEN is configured (and we're running as user account)
        helper_bot = None
        if CONFIG.login.BOT_TOKEN:
            helper_bot = TelegramClient(
                "helper_bot", CONFIG.login.API_ID, CONFIG.login.API_HASH,
                connection_retries=connection_retries,
                retry_delay=30,
            )
            await helper_bot.start(bot_token=CONFIG.login.BOT_TOKEN)
            logging.info("Helper bot started — will take over sending on primary FloodWait.")
        else:
            logging.info("No BOT_TOKEN configured — running without helper bot.")
        config.from_to = await config.load_from_to(client, config.CONFIG.forwards)
        client: TelegramClient
        unavailable_channels = []
        finished_channels = []

        # Build the initial queue: list of (resume_at, forward, src, dest)
        # resume_at=0 means ready immediately
        queue = []
        for (src, dest), forward in zip(config.from_to.items(), config.CONFIG.forwards):
            queue.append((0.0, forward, src, dest))

        while queue:
            # Sort by resume_at so the earliest-ready source comes first
            queue.sort(key=lambda x: x[0])
            resume_at, forward, src, dest = queue.pop(0)

            # If this source isn't ready yet, wait out the remaining time
            wait_remaining = resume_at - time.time()
            if wait_remaining > 0:
                logging.info(
                    f"All sources are deferred. Waiting {wait_remaining:.0f}s "
                    f"before resuming next source..."
                )
                await asyncio.sleep(wait_remaining)

            # Resolve channel name
            try:
                src_entity = await client.get_entity(src)
                real_name = getattr(src_entity, 'title', getattr(src_entity, 'username', str(src)))
            except Exception:
                real_name = str(src)
            con_name = forward.con_name if forward.con_name else "Unnamed"
            label = f"{src} (Real: {real_name}, Config: {con_name})"

            logging.info(f"Forwarding messages from {label} to {dest}")
            last_id = 0
            flood_wait_hit = False

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
                    # Prefer bot if available; fall back to primary on bot FloodWait
                    active_sender = helper_bot  # None = primary; helper_bot = bot
                    bot_flood_until = 0.0      # timestamp when bot's ban expires
                    primary_flood_until = 0.0  # timestamp when primary's ban expires
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
                                    r_stored = st.stored.get(r_event_uid)
                                    if r_stored:
                                        tm.reply_to = r_stored.get(d)
                                fwded_msg = await send_message(d, tm, sender_client=active_sender)
                                st.stored[event_uid].update({d: fwded_msg.id})
                            tm.clear()
                            last_id = message.id
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
                            resume_time = time.time() + fwe.seconds

                            if active_sender is helper_bot:
                                # Bot hit FloodWait — fall back to primary if available
                                bot_flood_until = resume_time
                                if time.time() >= primary_flood_until:
                                    logging.warning(
                                        f"Bot FloodWait {fwe.seconds}s — falling back to primary: {msg_link}"
                                    )
                                    active_sender = None  # use primary
                                    # Retry immediately with primary (loop continues)
                                else:
                                    # Primary also rate-limited — defer
                                    earliest = min(primary_flood_until, resume_time)
                                    logging.warning(
                                        f"Bot FloodWait {fwe.seconds}s — both accounts rate-limited: {msg_link}\n"
                                        f"  Skipping to next source. Will resume in {earliest - time.time():.0f}s."
                                    )
                                    active_sender = helper_bot  # reset to preferred for next attempt
                                    queue.append((earliest, forward, src, dest))
                                    flood_wait_hit = True
                                    break

                            else:
                                # Primary hit FloodWait — try switching to bot if available
                                primary_flood_until = resume_time
                                if helper_bot and time.time() >= bot_flood_until:
                                    logging.warning(
                                        f"Primary FloodWait {fwe.seconds}s — switching to helper bot: {msg_link}"
                                    )
                                    active_sender = helper_bot
                                    # Retry immediately with bot (loop continues)
                                else:
                                    # No bot or bot also rate-limited — defer
                                    earliest = min(primary_flood_until, bot_flood_until) if helper_bot else primary_flood_until
                                    logging.warning(
                                        f"Primary FloodWait {fwe.seconds}s — both accounts rate-limited: {msg_link}\n"
                                        f"  Skipping to next source. Will resume in {earliest - time.time():.0f}s."
                                    )
                                    active_sender = helper_bot  # reset to preferred for next attempt
                                    queue.append((earliest, forward, src, dest))
                                    flood_wait_hit = True
                                    break

                        except MediaEmptyError:
                            if active_sender is helper_bot:
                                # Bot can't reference media from user's session — fall back to primary
                                logging.warning(
                                    f"Bot cannot send media for message {message.id} "
                                    f"(media reference is tied to user session) — falling back to primary."
                                )
                                active_sender = None  # retry with primary
                            else:
                                # Primary also can't send this media — skip
                                logging.warning(
                                    f"Skipping message {message.id}: media is unavailable or expired."
                                )
                                last_id = message.id
                                forward.offset = last_id
                                write_config(CONFIG, persist=False)
                                break

                        except Exception as err:
                            logging.exception(err)
                            break  # skip on unknown error

                    if flood_wait_hit:
                        break  # break out of iter_messages loop, move to next source

                if not flood_wait_hit:
                    finished_channels.append(label)
                    logging.info(f"Finished forwarding messages from {label}")

            except ValueError as err:
                name = forward.con_name if forward.con_name else str(src)
                logging.error(f"Could not access source {src} ({name}): {err}")
                unavailable_channels.append(f"{src} ({name})")

        if finished_channels:
            logging.info("=== Past mode complete. Channels processed: ===")
            for ch in finished_channels:
                logging.info(f"  ✓ {ch}")
        if unavailable_channels:
            logging.error("=== Unavailable channels (could not access): ===")
            for ch in unavailable_channels:
                logging.error(f"  ✗ {ch}")