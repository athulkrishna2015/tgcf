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


_cached_proxy_config = None
_dead_proxies = set()


def invalidate_proxy():
    """Mark the currently cached proxy as dead and clear the cache."""
    global _cached_proxy_config, _dead_proxies
    if _cached_proxy_config and "proxy" in _cached_proxy_config:
        p = _cached_proxy_config["proxy"]
        if isinstance(p, tuple):  # MTProto proxy tuple: (host, port, secret)
            _dead_proxies.add((p[0], p[1]))
            logging.info(f"Proxy {p[0]}:{p[1]} marked as dead.")
            update_proxy_health(p[0], p[1], success=False)
        elif isinstance(p, dict):  # Standard proxy dict
            _dead_proxies.add((p.get("addr"), p.get("port")))
            logging.info(f"Proxy {p.get('addr')}:{p.get('port')} marked as dead.")
            update_proxy_health(p.get("addr"), p.get("port"), success=False)
    _cached_proxy_config = None


def update_proxy_health(server, port, success: bool):
    """Update proxy health metrics (failures, status) in the local JSON cache."""
    import time
    import json
    cache_file = "tgcf.proxies.json"
    if not os.path.exists(cache_file):
        return
    try:
        with open(cache_file, "r") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "proxies" not in data:
            return
        
        updated = False
        proxies_list = []
        for p in data["proxies"]:
            # Standardize entry to dict format for backward compatibility
            if isinstance(p, dict):
                p_dict = p
            elif isinstance(p, (list, tuple)) and len(p) >= 2:
                p_dict = {
                    "server": p[0],
                    "port": p[1],
                    "secret": p[2] if len(p) > 2 else "",
                    "failures": 0,
                    "last_checked": 0.0,
                    "is_working": True
                }
            else:
                continue
                
            if p_dict.get("server") == server and p_dict.get("port") == port:
                p_dict["last_checked"] = time.time()
                if success:
                    p_dict["failures"] = 0
                    p_dict["is_working"] = True
                else:
                    p_dict["failures"] = p_dict.get("failures", 0) + 1
                    if p_dict["failures"] >= 3:
                        p_dict["is_working"] = False
                updated = True
            # Keep only working proxies in the JSON cache
            if p_dict.get("is_working", True) and p_dict.get("failures", 0) < 3:
                proxies_list.append(p_dict)
            else:
                updated = True  # We modified the list by removing a dead proxy
            
        if updated:
            data["proxies"] = proxies_list
            with open(cache_file, "w") as f:
                json.dump(data, f, indent=4)
    except Exception as e:
        logging.warning(f"Failed to update proxy health in cache: {e}")


def fetch_public_proxies():
    """Fetch MTProto proxies from the public list, using a local JSON cache."""
    import time
    import json
    import urllib.request
    import urllib.parse

    cache_file = "tgcf.proxies.json"
    
    # 1. Try loading from cache file first if it exists
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f:
                data = json.load(f)
                if isinstance(data, dict) and "proxies" in data:
                    logging.info("Loaded proxies list from local cache file.")
                    res = []
                    for p in data["proxies"]:
                        if isinstance(p, dict):
                            # Skip proxies marked as dead or having >= 3 failures
                            if p.get("is_working", True) and p.get("failures", 0) < 3:
                                res.append((p.get("server"), p.get("port"), p.get("secret")))
                        elif isinstance(p, (list, tuple)) and len(p) >= 3:
                            res.append((p[0], p[1], p[2]))
                    return res
        except Exception as e:
            logging.warning(f"Failed to read proxy cache: {e}")

    # 2. Cache is missing or outdated; fetch from github
    proxies = []
    url = "https://raw.githubusercontent.com/SoliSpirit/mtproto/master/all_proxies.txt"
    logging.info("Fetching public MTProto proxy list from GitHub...")
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            content = response.read().decode('utf-8')
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("https://t.me/proxy?") or line.startswith("tg://proxy?"):
                    parsed = urllib.parse.urlparse(line)
                    query = urllib.parse.parse_qs(parsed.query)
                    server = query.get("server", [None])[0]
                    port = query.get("port", [None])[0]
                    secret = query.get("secret", [None])[0]
                    if server and port and secret:
                        try:
                            proxies.append((server.strip(), int(port.strip()), secret.strip()))
                        except ValueError:
                            continue
        
        # Convert proxies to dicts for writing
        json_proxies = []
        for s, p, sec in proxies:
            json_proxies.append({
                "server": s,
                "port": p,
                "secret": sec,
                "failures": 0,
                "last_checked": 0.0,
                "is_working": True
            })
            
        # Save to local cache
        try:
            with open(cache_file, "w") as f:
                json.dump({"fetched_at": time.time(), "proxies": json_proxies}, f, indent=4)
            logging.info(f"Saved {len(proxies)} fetched proxies to local cache {cache_file}.")
        except Exception as e:
            logging.warning(f"Failed to save proxy cache: {e}")

    except Exception as e:
        logging.warning(f"Failed to fetch public proxy list from GitHub: {e}")
        # Fallback to expired cache if it exists
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r") as f:
                    data = json.load(f)
                    res = []
                    for p in data.get("proxies", []):
                        if isinstance(p, dict):
                            if p.get("is_working", True) and p.get("failures", 0) < 3:
                                res.append((p.get("server"), p.get("port"), p.get("secret")))
                        elif isinstance(p, (list, tuple)) and len(p) >= 3:
                            res.append((p[0], p[1], p[2]))
                    return res
            except Exception:
                pass
                
    return proxies


def find_working_proxy():
    """Find a working MTProto proxy by testing the fetched ones."""
    global _dead_proxies
    proxies = fetch_public_proxies()
    if not proxies:
        return None
    
    import socket
    try:
        timeout = float(os.getenv("TGCF_PROXY_CHECK_TIMEOUT", "1.5"))
    except ValueError:
        timeout = 1.5

    logging.info(f"Testing public MTProto proxies (excluding {len(_dead_proxies)} dead ones, timeout={timeout}s)...")
    # Filter out dead proxies
    available_proxies = [(s, p, sec) for s, p, sec in proxies if (s, p) not in _dead_proxies]

    for server, port, secret in available_proxies[:30]:  # Test first 30 active proxies
        try:
            with socket.create_connection((server, port), timeout=timeout):
                logging.info(f"Found active proxy: {server}:{port}")
                update_proxy_health(server, port, success=True)
                return (server, port, secret)
        except Exception:
            update_proxy_health(server, port, success=False)
            continue
    return None


def get_proxy_config():
    """Get proxy configuration for Telethon TelegramClient, only if connection is blocked."""
    global _cached_proxy_config
    if _cached_proxy_config is not None:
        return _cached_proxy_config

    proxy_host = os.getenv("TGCF_PROXY_HOST")
    proxy_port = os.getenv("TGCF_PROXY_PORT")
    proxy_type_str = os.getenv("TGCF_PROXY_TYPE", "").lower()
    
    # Check if we can connect to Telegram directly first
    import socket
    try:
        direct_timeout = float(os.getenv("TGCF_DIRECT_CHECK_TIMEOUT", "2.0"))
    except ValueError:
        direct_timeout = 2.0

    try:
        timeout = float(os.getenv("TGCF_PROXY_CHECK_TIMEOUT", "1.5"))
    except ValueError:
        timeout = 1.5

    telegram_ips = ["149.154.175.50", "91.108.56.154"]
    is_blocked = True
    for ip in telegram_ips:
        try:
            with socket.create_connection((ip, 443), timeout=direct_timeout):
                is_blocked = False
                break
        except Exception:
            continue

    if not is_blocked:
        logging.info("Direct connection to Telegram is working. Bypassing proxy settings.")
        _cached_proxy_config = {}
        return _cached_proxy_config

    logging.info("Direct connection to Telegram timed out/blocked.")

    # 1. Try user configured proxy in .env first
    if proxy_host and proxy_port:
        try:
            proxy_port_int = int(proxy_port)
            if (proxy_host, proxy_port_int) not in _dead_proxies:
                with socket.create_connection((proxy_host, proxy_port_int), timeout=timeout):
                    logging.info(f"User configured proxy {proxy_host}:{proxy_port_int} is active. Using it.")
                    if proxy_type_str == "mtproto":
                        proxy_secret = os.getenv("TGCF_PROXY_SECRET")
                        if proxy_secret:
                            from telethon.network.connection import ConnectionTcpMTProxyRandomizedIntermediate
                            _cached_proxy_config = {
                                "connection": ConnectionTcpMTProxyRandomizedIntermediate,
                                "proxy": (proxy_host, proxy_port_int, proxy_secret)
                            }
                            return _cached_proxy_config
                    else:
                        proxy_user = os.getenv("TGCF_PROXY_USER")
                        proxy_pass = os.getenv("TGCF_PROXY_PASSWORD") or os.getenv("TGCF_PROXY_PASS")
                        proxy_types = {"socks5": "socks5", "socks4": "socks4", "http": "http"}
                        proxy_type = proxy_types.get(proxy_type_str, "socks5")
                        proxy_dict = {"proxy_type": proxy_type, "addr": proxy_host, "port": proxy_port_int, "rdns": True}
                        if proxy_user: proxy_dict["username"] = proxy_user
                        if proxy_pass: proxy_dict["password"] = proxy_pass
                        _cached_proxy_config = {"proxy": proxy_dict}
                        return _cached_proxy_config
            else:
                logging.warning(f"User configured proxy {proxy_host}:{proxy_port} was previously marked as dead. Skipping to auto-fallback.")
        except Exception as e:
            logging.warning(f"User configured proxy {proxy_host}:{proxy_port} is offline/unreachable: {e}")

    # 2. Fallback to auto-fetching a working public MTProto proxy
    logging.info("Attempting to auto-fetch and locate a working public MTProto proxy...")
    working_proxy = find_working_proxy()
    if working_proxy:
        server, port, secret = working_proxy
        from telethon.network.connection import ConnectionTcpMTProxyRandomizedIntermediate
        _cached_proxy_config = {
            "connection": ConnectionTcpMTProxyRandomizedIntermediate,
            "proxy": (server, port, secret)
        }
        return _cached_proxy_config

    logging.error("Could not find any working proxy or establish connection to Telegram.")
    _cached_proxy_config = {}
    return _cached_proxy_config


async def update_proxies_from_channel(client: TelegramClient):
    """Fetch recent MTProto proxies from @ProxyMTProto channel and save them to cache."""
    import urllib.parse
    import json
    import time
    import re

    try:
        if await client.is_bot():
            return
        
        logging.info("Updating proxies list from @ProxyMTProto telegram channel...")
        proxies = []
        async for message in client.iter_messages("ProxyMTProto", limit=50):
            if message.text:
                # Find all tg://proxy or t.me/proxy links in the message text
                links = re.findall(r'(?:tg://proxy\?|t\.me/proxy\?|https://t\.me/proxy\?)[^\s"\'<]+', message.text)
                for link in links:
                    url_str = link
                    if url_str.startswith("tg://"):
                        url_str = url_str.replace("tg://", "http://")
                    elif not url_str.startswith("http"):
                        url_str = "http://" + url_str
                    
                    parsed = urllib.parse.urlparse(url_str)
                    query = urllib.parse.parse_qs(parsed.query)
                    server = query.get("server", [None])[0]
                    port = query.get("port", [None])[0]
                    secret = query.get("secret", [None])[0]
                    if server and port and secret:
                        try:
                            proxies.append((server.strip(), int(port.strip()), secret.strip()))
                        except ValueError:
                            continue
        if proxies:
            cache_file = "tgcf.proxies.json"
            existing = []
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, "r") as f:
                        data = json.load(f)
                        if isinstance(data, dict) and "proxies" in data:
                            for p in data["proxies"]:
                                if isinstance(p, dict):
                                    if p.get("is_working", True) and p.get("failures", 0) < 3:
                                        existing.append(p)
                                elif isinstance(p, (list, tuple)) and len(p) >= 3:
                                    existing.append({
                                        "server": p[0],
                                        "port": p[1],
                                        "secret": p[2],
                                        "failures": 0,
                                        "last_checked": 0.0,
                                        "is_working": True
                                    })
                except Exception:
                    pass
            
            seen = set()
            merged = []
            
            # Add new proxies from channel
            for s, p, sec in proxies:
                if (s, p) not in seen:
                    seen.add((s, p))
                    merged.append({
                        "server": s,
                        "port": p,
                        "secret": sec,
                        "failures": 0,
                        "last_checked": time.time(),
                        "is_working": True
                    })
                    
            # Add existing proxies
            for p in existing:
                s = p.get("server")
                port = p.get("port")
                if (s, port) not in seen:
                    seen.add((s, port))
                    merged.append(p)
            
            # Cap the list to prevent infinite growth
            merged = merged[:500]
                    
            with open(cache_file, "w") as f:
                json.dump({"fetched_at": time.time(), "proxies": merged}, f, indent=4)
            logging.info(f"Successfully added {len(proxies)} proxies from @ProxyMTProto channel to cache (capped at 500 total).")
    except Exception as e:
        logging.warning(f"Failed to update proxies from Telegram channel: {e}")


