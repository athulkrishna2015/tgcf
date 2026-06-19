"""Utility functions to smoothen your life."""

import logging
import os
import platform
import re
import sys
from datetime import datetime
from typing import TYPE_CHECKING

from telethon.client import TelegramClient
from telethon.hints import EntityLike
from telethon.tl.custom.message import Message

from tgcf import __version__
from tgcf.config import CONFIG
from tgcf.plugin_models import STYLE_CODES, PluginConfig

if TYPE_CHECKING:
    from tgcf.plugins import TgcfMessage


def platform_info():
    nl = "\n"
    return f"""Running tgcf {__version__}\
    \nPython {sys.version.replace(nl, "")}\
    \nOS {os.name}\
    \nPlatform {platform.system()} {platform.release()}\
    \n{platform.architecture()} {platform.processor()}"""


async def send_message(recipient: EntityLike, tm: "TgcfMessage") -> Message:
    """Forward or send a copy, depending on config."""
    client: TelegramClient = tm.message.client
    if CONFIG.show_forwarded_from:
        return await client.forward_messages(recipient, tm.message)
    if tm.new_file:
        message = await client.send_file(
            recipient, tm.new_file, caption=tm.text, reply_to=tm.reply_to
        )
        return message
    tm.message.text = tm.text
    return await client.send_message(recipient, tm.message, reply_to=tm.reply_to)


def is_batching_safe(plugins_config: PluginConfig = None) -> bool:
    """Check if batch forwarding is safe (no modifying plugins are active)."""
    modifying_plugins = ["fmt", "mark", "ocr", "replace", "caption"]
    for p in modifying_plugins:
        # Check if active globally
        global_active = False
        global_p = getattr(CONFIG.plugins, p, None)
        if global_p and getattr(global_p, "check", False):
            global_active = True

        # Check if active locally
        local_active = False
        if plugins_config is not None:
            local_p = getattr(plugins_config, p, None)
            if local_p and getattr(local_p, "check", False):
                local_active = True

        if global_active or local_active:
            return False
    return True


def cleanup(*files: str) -> None:
    """Delete the file names passed as args."""
    for file in files:
        try:
            os.remove(file)
        except FileNotFoundError:
            logging.info(f"File {file} does not exist, so cant delete it.")


def stamp(file: str, user: str) -> str:
    """Stamp the filename with the datetime, and user info."""
    now = str(datetime.now())
    outf = safe_name(f"{user} {now} {file}")
    try:
        os.rename(file, outf)
        return outf
    except Exception as err:
        logging.warning(f"Stamping file name failed for {file} to {outf}. \n {err}")


def safe_name(string: str) -> str:
    """Return safe file name.

    Certain characters in the file name can cause potential problems in rare scenarios.
    """
    return re.sub(pattern=r"[-!@#$%^&*()\s]", repl="_", string=string)


def match(pattern: str, string: str, regex: bool) -> bool:
    if regex:
        return bool(re.findall(pattern, string))
    return pattern in string


def replace(pattern: str, new: str, string: str, regex: bool) -> str:
    def fmt_repl(matched):
        style = new
        s = STYLE_CODES.get(style)
        return f"{s}{matched.group(0)}{s}"

    if regex:
        if new in STYLE_CODES:
            compliled_pattern = re.compile(pattern)
            return compliled_pattern.sub(repl=fmt_repl, string=string)
        return re.sub(pattern, new, string)
    else:
        return string.replace(pattern, new)


def clean_session_files():
    for item in os.listdir():
        if item.endswith(".session") or item.endswith(".session-journal"):
            os.remove(item)


def get_proxy_config():
    """Get proxy configuration for Telethon TelegramClient."""
    proxy_host = os.getenv("TGCF_PROXY_HOST")
    proxy_port = os.getenv("TGCF_PROXY_PORT")
    proxy_type_str = os.getenv("TGCF_PROXY_TYPE", "").lower()
    
    if not proxy_host or not proxy_port:
        return {}

    try:
        proxy_port = int(proxy_port)
    except ValueError:
        logging.warning("TGCF_PROXY_PORT must be an integer.")
        return {}

    if proxy_type_str == "mtproto":
        proxy_secret = os.getenv("TGCF_PROXY_SECRET")
        if not proxy_secret:
            logging.warning("TGCF_PROXY_SECRET is required for mtproto proxy.")
            return {}
        
        from telethon.network.connection import ConnectionTcpMTProxyRandomizedIntermediate
        return {
            "connection": ConnectionTcpMTProxyRandomizedIntermediate,
            "proxy": (proxy_host, proxy_port, proxy_secret)
        }
    
    proxy_user = os.getenv("TGCF_PROXY_USER")
    proxy_pass = os.getenv("TGCF_PROXY_PASSWORD") or os.getenv("TGCF_PROXY_PASS")

    proxy_types = {
        "socks5": "socks5",
        "socks4": "socks4",
        "http": "http",
    }
    proxy_type = proxy_types.get(proxy_type_str, "socks5")

    proxy_dict = {
        "proxy_type": proxy_type,
        "addr": proxy_host,
        "port": proxy_port,
        "rdns": True
    }
    if proxy_user:
        proxy_dict["username"] = proxy_user
    if proxy_pass:
        proxy_dict["password"] = proxy_pass

    return {"proxy": proxy_dict}

