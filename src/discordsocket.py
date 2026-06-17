import websocket, threading, json, time
from ._utility import gatewayProperties


class DiscordSocket(threading.Thread):
    def __init__(self, token: str) -> None:
        if ":" in token:
            token = token.split(":")[-1]
        self.token = token
        threading.Thread.__init__(self)
        self.ws = websocket.WebSocket()
        self.running = True

    def login(self):
        self.ws.connect("wss://gateway.discord.gg/?encoding=json&v=9")
        interval = self.recieve()["d"]["heartbeat_interval"] / 1000
        threading.Thread(target=self.heartbeat, args=(interval,)).start()

    def heartbeat(self, interval: float):
        while self.running:
            time.sleep(interval)
            self.send_payload({"op": 1, "d": None})

    def recieve(self):
        data = self.ws.recv()
        if data:
            return json.loads(data)

    def send_payload(self, data: dict):
        self.ws.send(json.dumps(data))

    def online(self):
        self.send_payload(
            {
                "op": 2,
                "d": {
                    "token": self.token,
                    "capabilities": 125,
                    "properties": gatewayProperties(),
                    "presence": {
                        "status": "online",
                        "since": 0,
                        "activities": [
                            {
                                "name": "Custom Status",
                                "type": 4,
                                "state": "flank4r is here......",
                                "emoji": None,
                            }
                        ],
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
        )

    def _identify_payload(
        self, capabilities: int, presence: dict, client_state: dict
    ) -> dict:
        """Builds an IDENTIFY (op 2) keeping the browser identity in lockstep with
        the HTTP layer via gatewayProperties(); only the feature flags differ."""
        return {
            "op": 2,
            "d": {
                "token": self.token,
                "capabilities": capabilities,
                "properties": gatewayProperties(),
                "presence": presence,
                "compress": False,
                "client_state": client_state,
            },
        }

    def get_session_id(self, retries: int = 3):
        """Opens a short-lived gateway connection, sends IDENTIFY and returns the
        session_id from the READY event. Modern Discord requires this session_id in
        the join payload — the 2022 joiner posted an empty body, which no longer works.
        Mirrors the Go joiner's ConnectWebsocket: connect, identify, read until we
        see a session_id — retrying on a dropped connection, returning None if all
        attempts fail so the caller degrades gracefully instead of crashing."""
        identify = self._identify_payload(
            125,
            {"status": "online", "since": 0, "activities": [], "afk": False},
            {
                "guild_hashes": {},
                "highest_last_message_id": "0",
                "read_state_version": 0,
                "user_guild_settings_version": -1,
                "user_settings_version": -1,
            },
        )
        for _ in range(retries):
            try:
                self.ws = websocket.WebSocket()
                self.ws.connect(
                    "wss://gateway.discord.gg/?encoding=json&v=9",
                    origin="https://discord.com",
                )
                self.recieve()
                self.send_payload(identify)
                while True:
                    data = self.recieve()
                    if (
                        data
                        and isinstance(data.get("d"), dict)
                        and "session_id" in data["d"]
                    ):
                        return data["d"]["session_id"]
            except Exception:
                time.sleep(1)
            finally:
                try:
                    self.ws.close()
                except Exception:
                    pass
        return None

    def get_guild_channels(self, guild_id: str, retries: int = 3):
        """Opens a short-lived gateway connection, identifies, and pulls the guild's
        channel ids — plus the session_id — out of the READY event. Mirrors the Go
        FetchGuildChannels, used to scan every channel for verification gates.
        Retries on a dropped connection; returns (None, []) if all attempts fail.
        Returns (session_id, [channel_ids])."""
        identify = self._identify_payload(
            16381,
            {"status": "online", "since": 0, "activities": [], "afk": False},
            {
                "guild_versions": {},
                "highest_last_message_id": "0",
                "read_state_version": 0,
                "user_guild_settings_version": -1,
                "user_settings_version": -1,
                "private_channels_version": "0",
                "api_code_version": 0,
            },
        )
        for _ in range(retries):
            try:
                self.ws = websocket.WebSocket()
                self.ws.connect(
                    "wss://gateway.discord.gg/?encoding=json&v=9",
                    origin="https://discord.com",
                )
                self.recieve()
                self.send_payload(identify)
                while True:
                    data = self.recieve()
                    if not data or data.get("t") != "READY":
                        continue
                    d = data.get("d", {})
                    session_id = d.get("session_id")
                    channel_ids = []
                    for guild in d.get("guilds", []):
                        if guild.get("id") != guild_id:
                            continue
                        for channel in guild.get("channels", []):
                            cid = channel.get("id")
                            if cid:
                                channel_ids.append(cid)
                    return session_id, channel_ids
            except Exception:
                time.sleep(1)
            finally:
                try:
                    self.ws.close()
                except Exception:
                    pass
        return None, []

    def join_vc(self, channel_id: str, guild_id: str):
        self.send_payload(
            {
                "op": 4,
                "d": {
                    "guild_id": guild_id,
                    "channel_id": channel_id,
                    "self_mute": True,
                    "self_deaf": True,
                    "self_stream?": True,
                    "self_video": False,
                },
            }
        )
        self.send_payload(
            {
                "op": 18,
                "d": {
                    "type": "guild",
                    "guild_id": guild_id,
                    "channel_id": channel_id,
                    "preferred_region": "singapore",
                },
            }
        )
        time.sleep(3)
        self.running = False
        self.ws.close()

    def run(self, channel_id: str, guild_id: str):
        self.login()
        self.online()
        self.join_vc(channel_id, guild_id)
