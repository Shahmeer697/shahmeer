# Credits to the original author: https://github.com/Aniell4/MassDN/blob/main/scrape.py
# Scraping logic ported from the Go implementation at github.com/shahzain345/raidx (private)
# For more info about lazy guilds check out: https://luna.gitlab.io/discord-unofficial-docs/docs/lazy_guilds
import websocket
import json
import threading
import time
from ._utility import MPrint, USER_AGENT, gatewayProperties
from .global_variables import *

console = MPrint()

GATEWAY_URL = "wss://gateway.discord.gg/?encoding=json&v=9"

SOCKET_HEADERS = [
    "Accept-Encoding: gzip, deflate, br",
    "Accept-Language: en-US,en;q=0.9",
    "Cache-Control: no-cache",
    "Pragma: no-cache",
    "Sec-WebSocket-Extensions: permessage-deflate; client_max_window_bits",
    f"User-Agent: {USER_AGENT}",
]


class LazyGuildScraper:
    """
    Discord lazy guild member scraper (OP 14 / GUILD_MEMBER_LIST_UPDATE).

    Ported from the Go `LazyGuildScraper`. Adds deduplication, auto-reconnect,
    member-count-aware ranges and adaptive range-jumping when scraping stalls.
    """

    def __init__(self, token: str, guild_id: str, channel_id: str, scrape_field: str = "id"):
        if ":" in token:
            token = token.split(":")[-1]
        self.token = token
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.scrape_field = scrape_field

        self.members = {}
        self.ranges = [[0, 99]]  # start with the first 100 members
        self.last_range_idx = 0
        self.member_count = 0
        self.range_counter = 0
        self.max_ranges = 200
        self.last_seq = None

        self.reconnects = 0
        self.max_reconnects = 3

        self.ws = None
        self._lock = threading.Lock()
        self._done = threading.Event()  # set when scraping is finished/exhausted
        self._stop = threading.Event()  # set to tear down worker threads

    # ---- connection -------------------------------------------------------
    def connect(self):
        """Open the gateway, read HELLO and send IDENTIFY. Returns the heartbeat interval (seconds)."""
        self.ws = websocket.create_connection(
            GATEWAY_URL, header=SOCKET_HEADERS, enable_multithread=True
        )

        hello = json.loads(self.ws.recv())
        heartbeat_interval = hello["d"]["heartbeat_interval"] / 1000

        identify = {
            "op": 2,
            "d": {
                "token": self.token,
                "capabilities": 125,
                "properties": gatewayProperties(),
                "presence": {
                    "status": "online",
                    "since": 0,
                    "activities": [],
                    "afk": False,
                },
                "compress": False,
                "client_state": {
                    "guild_hashes": {},
                    "highest_last_message_id": "0",
                    "read_state_version": 0,
                    "user_guild_settings_version": -1,
                    "user_settings_version": -1,
                },
            },
        }
        self.ws.send(json.dumps(identify))
        return heartbeat_interval

    # ---- requests ---------------------------------------------------------
    def send_lazy_request(self):
        """Send an OP 14 request for the current ranges."""
        with self._lock:
            ranges = [list(r) for r in self.ranges]
        payload = {
            "op": 14,
            "d": {
                "guild_id": self.guild_id,
                "typing": True,
                "threads": False,
                "activities": True,
                "members": [],
                "channels": {self.channel_id: ranges},
            },
        }
        self.ws.send(json.dumps(payload))

    def get_ranges(self, index: int, multiplier: int):
        """Generate the next ranges, always keeping [0, 99] present (mirrors the Go GetRanges)."""
        initial = int(index * multiplier)
        ranges = [[initial, initial + 99]]
        if self.member_count > initial + 99:
            ranges.append([initial + 100, initial + 199])
        if [0, 99] not in ranges:
            ranges.insert(0, [0, 99])
        return ranges

    def request_next_range(self):
        """Advance to and request the next range. Raises RuntimeError once max_ranges is hit."""
        with self._lock:
            if self.range_counter >= self.max_ranges:
                raise RuntimeError(
                    f"reached maximum number of range requests ({self.max_ranges})"
                )
            self.last_range_idx += 1
            self.ranges = self.get_ranges(self.last_range_idx, 100)
            self.range_counter += 1
        self.send_lazy_request()

    # ---- member handling --------------------------------------------------
    def add_member(self, user: dict, nick=None) -> bool:
        """Add a member if not already seen. Returns True if it was new."""
        if self.scrape_field == "avatar":
            user_id = user.get("id")
            avatar = user.get("avatar")
            if not user_id or not avatar:
                return False
            uid = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar}.webp"
        else:
            uid = user.get(self.scrape_field)
        if not uid:
            return False
        with self._lock:
            if uid in self.members:
                return False
            tag = user.get("username", "")
            discrim = user.get("discriminator")
            if discrim and discrim != "0":
                tag = f"{tag}#{discrim}"
            self.members[uid] = {"tag": tag, "id": uid, "nick": nick}
        return True

    def process_member_list_update(self, decoded: dict) -> int:
        """Process a GUILD_MEMBER_LIST_UPDATE event. Returns the number of newly added members."""
        d = decoded.get("d", {})
        if d.get("guild_id") != self.guild_id:
            return 0

        if d.get("member_count", 0) > 0:
            with self._lock:
                self.member_count = d["member_count"]

        added = 0
        for op in d.get("ops", []):
            if op.get("op") != "SYNC":
                continue
            items = op.get("items", [])
            if not items:
                continue
            for item in items:
                member = item.get("member") if isinstance(item, dict) else None
                if member and member.get("user", {}).get(self.scrape_field):
                    if self.add_member(member["user"], member.get("nick")):
                        added += 1
        return added

    # ---- worker loops -----------------------------------------------------
    def heartbeat(self, interval: float):
        """Send heartbeats until told to stop. Reads self.ws each tick so it survives reconnects."""
        while not self._stop.wait(interval):
            try:
                self.ws.send(json.dumps({"op": 1, "d": self.last_seq}))
            except Exception:
                return

    def listen(self):
        """Read and dispatch gateway messages, reconnecting on abnormal closure."""
        while not self._stop.is_set():
            try:
                raw = self.ws.recv()
            except Exception as e:
                if self._stop.is_set():
                    return
                if self.reconnects < self.max_reconnects:
                    self.reconnects += 1
                    console.w_print(
                        f"Discord closed connection: {e} - attempting to reconnect ({self.reconnects}/{self.max_reconnects})..."
                    )
                    with self._lock:
                        if len(self.ranges) > 1:
                            self.ranges = self.ranges[:1]
                    try:
                        self.connect()
                        console.s_print("Successfully reconnected to Discord")
                        continue
                    except Exception as re:
                        console.f_print(f"Failed to reconnect: {re}")
                        self._done.set()
                        return
                console.f_print(f"Error reading message: {e}")
                self._done.set()
                return

            if not raw:
                continue
            try:
                decoded = json.loads(raw)
            except Exception as e:
                console.w_print(f"Error parsing message: {e}")
                continue
            if decoded is None:
                continue

            if decoded.get("s") is not None:
                self.last_seq = decoded["s"]

            op = decoded.get("op")
            if op == 0:  # Dispatch
                t = decoded.get("t")
                if t == "READY":
                    for g in decoded["d"].get("guilds", []):
                        if g.get("id") == self.guild_id:
                            self.member_count = g.get("member_count", 0)
                elif t == "READY_SUPPLEMENTAL":
                    console.s_print("Connection ready, sending lazy request")
                    with self._lock:
                        self.ranges = self.get_ranges(0, 100)
                    try:
                        self.send_lazy_request()
                    except Exception as e:
                        console.f_print(f"Error sending lazy request: {e}")
                        self._done.set()
                        return
                elif t == "GUILD_MEMBER_LIST_UPDATE":
                    added = self.process_member_list_update(decoded)
                    if added > 0:
                        console.s_print(
                            f"Added {added} new unique members (total: {len(self.members)})"
                        )

    def range_loop(self):
        """Drive range requests, jumping to new positions when scraping stalls (mirrors the Go goroutine)."""
        time.sleep(3)

        consecutive_no_new = 0
        last_count = 0
        restart_attempts = 0
        max_restart_attempts = 3

        while not self._stop.wait(0.35):
            with self._lock:
                count = len(self.members)
            if count == 0:
                continue

            if count > last_count:
                console.s_print(
                    f"Currently scraped {count} unique members, requesting next range..."
                )
                consecutive_no_new = 0
            else:
                consecutive_no_new += 1
                console.w_print(
                    f"No new members since last request ({consecutive_no_new} consecutive empty results)"
                )

                if consecutive_no_new >= 5 and restart_attempts < max_restart_attempts:
                    restart_attempts += 1
                    consecutive_no_new = 0
                    jump_multiplier = (
                        200 * restart_attempts
                        if count < 500
                        else 1000 * restart_attempts
                    )
                    with self._lock:
                        self.last_range_idx = jump_multiplier // 100
                        self.ranges = self.get_ranges(self.last_range_idx, 100)
                    console.s_print(
                        f"Restarting at range index {self.last_range_idx} to find more members "
                        f"(attempt {restart_attempts}/{max_restart_attempts})"
                    )

                if consecutive_no_new >= 5 and restart_attempts >= max_restart_attempts:
                    console.s_print(
                        f"No new members found after {max_restart_attempts} restart attempts, stopping scraper"
                    )
                    self._done.set()
                    return

            last_count = count

            try:
                self.request_next_range()
            except RuntimeError as e:
                console.w_print(f"Error requesting next range: {e}")
                console.s_print("Reached maximum range requests, saving results")
                self._done.set()
                return
            except Exception as e:
                console.w_print(f"Error requesting next range: {e}")
                with self._lock:
                    self.last_range_idx += 1


def scrape(token: str, guild_id: str, channel_id: str, scrape_field: str = "id"):
    """
    Scrape unique members of a guild and return them as a dict keyed by the
    chosen field ({value: {"tag", "id", "nick"}}). Iterating the result yields
    the keys, matching what main.py expects. scrape_field defaults to "id";
    pass "global_name" to scrape global names instead.
    """
    scraper = LazyGuildScraper(token, guild_id, channel_id, scrape_field)

    console.s_print("Connecting to Discord gateway...")
    try:
        interval = scraper.connect()
    except Exception as e:
        console.f_print(f"Failed to connect: {e}")
        return scraper.members
    console.s_print("Connected to Discord gateway")

    threading.Thread(target=scraper.heartbeat, args=(interval,), daemon=True).start()
    threading.Thread(target=scraper.listen, daemon=True).start()
    threading.Thread(target=scraper.range_loop, daemon=True).start()

    scraper._done.wait(timeout=1800)
    if not scraper._done.is_set():
        console.w_print("Maximum scraping time reached (30 minutes)")

    scraper._stop.set()
    try:
        if scraper.ws:
            scraper.ws.close()
    except Exception:
        pass

    console.s_print(f"Scraping completed. Total unique members: {len(scraper.members)}")
    return scraper.members
