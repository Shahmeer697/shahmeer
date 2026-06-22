"""
Copyright 2022 Shahzain Masood

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""

from httpz import AsyncClient
from ._utility import Utility, MPrint, USER_AGENT, BUILD_NUM
from ._captcha import Captcha
from ._trackers import AntiTracking
from base64 import b64encode as encoder, urlsafe_b64encode
from colorama import Fore, Style
from .discordsocket import DiscordSocket
import os
import re
import uuid
import hashlib
import random
import string
import time
import asyncio
import json as jsonLib
from urllib.parse import quote
from datetime import datetime, timedelta, timezone

console = MPrint()
console.s_print(f"Discord is currently on build: {BUILD_NUM}")
time.sleep(1.5)


class MultiTool:
    """
    # Multitool main class
    """

    async def _init(self, token: str):
        self._utility = Utility()
        self._anti_tracking = AntiTracking(BUILD_NUM)

        if ":" in token:
            token = token.split(":")[-1]

        self._launch_id = str(uuid.uuid4())
        self._launch_signature = str(uuid.uuid4())
        self._heartbeat_session_id = str(uuid.uuid4())

        self.client = AsyncClient(
            cookies={"locale": self._anti_tracking.lang},
            headers={
                "Host": "discord.com",
                "User-Agent": self._anti_tracking.ua,
                "Accept": "*/*",
                "Accept-Language": f"{self._anti_tracking.lang},en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br, zstd",
            },
            timeout=self._utility.config["requestTimeout"],
            proxy=self._utility.proxy,
            ja3=self._anti_tracking.ja3,
            h2_fingerprint=self._anti_tracking.akamai,
            browser="firefox",
        )
        self.token = token

        self.client.headers["X-Super-Properties"] = self._anti_tracking.super_props
        res = await self.client.get("https://discord.com/api/v9/experiments")
        try:
            self.client.headers["X-Fingerprint"] = res.json().get("fingerprint")
        except Exception:
            pass
        self.client.headers["Authorization"] = token
        self.client.headers["Origin"] = "https://discord.com"
        self.client.headers["Referer"] = "https://discord.com/channels/@me"
        self.client.headers["X-Discord-Locale"] = self._anti_tracking.lang
        self.client.headers["X-Discord-Timezone"] = self._anti_tracking.timezone
        self.client.headers["X-Debug-Options"] = "bugReporterEnabled"
        self.client.headers["X-Installation-ID"] = (
            res.json().get("installation")
            if "installation" in res.text
            else self.__generate_installation_id()
        )
        self._captcha = Captcha()

    def _build_super_properties(self) -> str:
        """Builds the base64-encoded X-Super-Properties header — the client
        fingerprint Discord validates on every request.

        Field order and value types mirror a real Firefox client exactly (e.g.
        client_build_number must be an int, not a quoted string), since any
        deviation is a detection signal.
        """
        properties = {
            "os": "Windows",
            "browser": "Firefox",
            "device": "",
            "system_locale": "en-US",
            "has_client_mods": False,
            "browser_user_agent": USER_AGENT,
            "browser_version": "151.0",
            "os_version": "10",
            "referrer": "",
            "referring_domain": "",
            "referrer_current": "https://discord.com/",
            "referring_domain_current": "discord.com",
            "release_channel": "stable",
            "client_build_number": int(BUILD_NUM),
            "client_event_source": None,
            "client_launch_id": self._launch_id,
            "launch_signature": self._launch_signature,
            "client_heartbeat_session_id": self._heartbeat_session_id,
            "client_app_state": "focused",
        }
        return encoder(
            jsonLib.dumps(properties, separators=(",", ":")).encode()
        ).decode()

    def __generate_installation_id(self) -> str:
        """Builds an X-Installation-ID in Discord's format: a snowflake, a dot,
        then 20 random bytes as unpadded base64url."""
        suffix = urlsafe_b64encode(os.urandom(20)).decode().rstrip("=")
        return f"{self.__generate_nonce()}.{suffix}"

    async def join(self, rawInvite: str, ctxProperties: str):
        self.client.headers["Referer"] = "https://discord.com/channels/@me"
        self.client.headers["X-Context-Properties"] = ctxProperties
        sessionId = await asyncio.to_thread(DiscordSocket(self.token).get_session_id)
        if sessionId is None:
            console.w_print(
                f"{self.token} couldn't grab a gateway session_id; attempting join anyway"
            )
        req = await self.client.post(
            f"https://discord.com/api/v9/invites/{rawInvite}",
            json={"session_id": sessionId},
        )
        data = req.json()
        if "captcha_key" not in data:
            self.client.headers.pop("X-Context-Properties", None)
            self.client.headers.pop("Referer", None)
            if data.get("message") == "The user is banned from this guild.":
                console.f_print(f"{self.token} is banned from this server.")
                return False, req
            console.s_print(f"{self.token} successfully joined discord.gg/{rawInvite}")
            return True, req
        console.w_print(
            f"{self.token} captcha detected. solving thru {self._utility.config.get('captcha').get('api')}"
        )
        captcha_sitekey = data["captcha_sitekey"]
        captcha_rqtoken = data["captcha_rqtoken"]
        captcha_rqdata = data["captcha_rqdata"]
        captcha_session_id = data["captcha_session_id"]

        captcha_key = await self._captcha.getCaptchaPrivate(data, self._utility.proxy)
        self.client.headers["X-Captcha-Key"] = captcha_key
        self.client.headers["X-Captcha-Rqtoken"] = captcha_rqtoken
        self.client.headers["X-Captcha-Session-Id"] = captcha_session_id
        req = await self.client.post(
            f"https://discord.com/api/v9/invites/{rawInvite}",
            json={
                "session_id": sessionId,
            },
        )
        self.client.headers.pop("X-Context-Properties", None)
        self.client.headers.pop("X-Captcha-Key", None)
        self.client.headers.pop("X-Captcha-Rqtoken", None)
        self.client.headers.pop("X-Captcha-Session-Id", None)
        if req.status_code == 200:
            console.s_print(f"{self.token} successfully joined discord.gg/{rawInvite}")
            return True, req
        else:
            console.f_print(f"{self.token} failed to join discord.gg/{rawInvite}")
            return False, req

    async def bypassScreening(self, guildId: str, rawInvite: str):
        req = await self.client.get(
            f"https://discord.com/api/v9/guilds/{guildId}/member-verification?with_guild=false&invite_code={rawInvite}"
        )
        if req.status_code != 200:
            console.f_print(f"{self.token} failed to bypass membership screening!")
            return False
        req = await self.client.put(
            f"https://discord.com/api/v9/guilds/{guildId}/requests/@me", json=req.json()
        )
        console.s_print(
            f"{self.token} bypassed membership screening for {guildId}(discord.gg/{rawInvite}) successfully!"
        )
        return True

    async def bypassOnboarding(self, guildId: str):
        """Ports the Go bypassOnboarding: fetch the guild's onboarding prompts,
        mark every prompt/option as seen, pick a random option per prompt and
        submit the responses to satisfy the onboarding gate."""
        req = await self.client.get(
            f"https://discord.com/api/v9/guilds/{guildId}/onboarding"
        )
        if req.status_code != 200:
            console.f_print(f"{self.token} failed to fetch onboarding for {guildId}")
            return False
        data = req.json()
        timeId = int(time.time() * 1000)
        payload = {
            "onboarding_responses": [],
            "onboarding_prompts_seen": {},
            "onboarding_responses_seen": {},
        }
        for prompt in data.get("prompts", []):
            promptId = prompt.get("id")
            if not promptId:
                continue
            payload["onboarding_prompts_seen"][promptId] = timeId
            optionIds = []
            for option in prompt.get("options", []):
                optionId = option.get("id")
                if not optionId:
                    continue
                optionIds.append(optionId)
                payload["onboarding_responses_seen"][optionId] = timeId
            if optionIds:
                payload["onboarding_responses"].append(random.choice(optionIds))
        req = await self.client.post(
            f"https://discord.com/api/v9/guilds/{guildId}/onboarding-responses",
            json=payload,
        )
        if req.status_code == 200:
            console.s_print(
                f"{self.token} bypassed onboarding for {guildId} successfully!"
            )
            return True
        console.f_print(f"{self.token} failed to bypass onboarding for {guildId}")
        return False

    async def bypassDoubleCounter(self):
        """Ports the Go bypassDoubleCounter: DM the DoubleCounter bot, read its
        latest embed, pull the verification link out of the 'Status' field and
        solve it through Scrappey (up to 3 attempts)."""
        channelId, _ = await self.__open_dm("703886990948565003")
        if channelId is None:
            return False
        req = await self.client.get(
            f"https://discord.com/api/v9/channels/{channelId}/messages?limit=1"
        )
        messages = req.json()
        if not isinstance(messages, list):
            return False
        scrapperKey = self._utility.config.get("joiner", {}).get("scrapperApiKey")
        for message in messages:
            try:
                timestamp = datetime.fromisoformat(message["timestamp"])
            except Exception:
                continue
            if datetime.now(timezone.utc) - timestamp > timedelta(minutes=2):
                continue
            for embed in message.get("embeds", []):
                for field in embed.get("fields", []):
                    if field.get("name") != "Status":
                        continue
                    match = re.search(r"\((https?://[^\)]+)\)", field.get("value", ""))
                    if not match:
                        continue
                    link = match.group(1)
                    scrapper = AsyncClient(timeout=120)
                    for _ in range(3):
                        res = await scrapper.post(
                            f"https://publisher.scrappey.com/api/v1?key={scrapperKey}",
                            json={"cmd": "request.get", "url": link},
                        )
                        solution = res.json().get("solution", {})
                        if solution.get("verified"):
                            console.s_print(
                                f"{self.token} bypassed double counter successfully!"
                            )
                            return True
        console.f_print(f"{self.token} failed to bypass double counter")
        return False

    async def buttonAndEmojiVerification(self, guildId: str):
        """Ports the Go basic joiner's emoji/button verification: fetch every
        channel in the guild plus a live session_id from one gateway READY, then
        scan each channel — reacting to verification emojis and clicking
        verification buttons. The user never has to pick a channel."""
        sessionId, channels = await asyncio.to_thread(
            DiscordSocket(self.token).get_guild_channels, guildId
        )
        if not channels:
            console.f_print(f"{self.token} found no channels to scan in {guildId}")
            return False
        emojiVerified = False
        buttonVerified = False
        for channelId in channels:
            e, b = await self.__scanChannelForVerification(
                channelId, guildId, sessionId
            )
            emojiVerified = emojiVerified or e
            buttonVerified = buttonVerified or b
        return emojiVerified or buttonVerified

    async def __scanChannelForVerification(
        self, channelId: str, guildId: str, sessionId: str
    ):
        """Scans one channel's recent messages: react to the first few emoji
        reactions and click any verification buttons (component interactions).
        Covers both 'react to verify' and 'click the button to verify' gates."""
        emojiVerified = False
        buttonVerified = False
        req = await self.client.get(
            f"https://discord.com/api/v9/channels/{channelId}/messages?limit=4"
        )
        if req.status_code != 200:
            return emojiVerified, buttonVerified
        messages = req.json()
        if not isinstance(messages, list):
            return emojiVerified, buttonVerified
        for message in messages:
            messageId = message["id"]
            flags = message.get("flags", 0)
            for reaction in message.get("reactions", [])[:3]:
                emojiObj = reaction["emoji"]
                emojiName = emojiObj["name"]
                if emojiObj.get("id"):
                    reactUrl = (
                        f"https://discord.com/api/v9/channels/{channelId}/messages/{messageId}"
                        f"/reactions/{emojiName}%3A{emojiObj['id']}/%40me?location=Message%20Inline%20Button&type=0"
                    )
                else:
                    reactUrl = (
                        f"https://discord.com/api/v9/channels/{channelId}/messages/{messageId}"
                        f"/reactions/{quote(emojiName)}/%40me?location=Message%20Inline%20Button&type=0"
                    )
                res = await self.client.put(reactUrl)
                if res.status_code == 204:
                    emojiVerified = True
            for component in message.get("components", []):
                for sub in component.get("components", []):
                    if sub.get("type") != 2:
                        continue
                    customId = sub.get("custom_id")
                    if not customId:
                        continue
                    payload = {
                        "type": 3,
                        "nonce": self.__generate_nonce(),
                        "guild_id": guildId,
                        "channel_id": channelId,
                        "message_flags": flags,
                        "message_id": messageId,
                        "application_id": message["author"]["id"],
                        "session_id": sessionId,
                        "data": {"component_type": 2, "custom_id": customId},
                    }
                    res = await self.client.post(
                        "https://discord.com/api/v9/interactions", json=payload
                    )
                    if res.status_code == 204:
                        buttonVerified = True
        if emojiVerified:
            console.s_print(f"{self.token} passed emoji verification in {channelId}")
        if buttonVerified:
            console.s_print(f"{self.token} passed button verification in {channelId}")
        return emojiVerified, buttonVerified

    def __generate_nonce(self):
        """Returns a Discord snowflake-style nonce: ms since the Discord epoch shifted left 22 bits,
        OR'd with 22 random low bits. Required for sending messages."""
        DISCORD_EPOCH = 1420070400000
        current_time = int(time.time() * 1000)
        nonce_timestamp = (current_time - DISCORD_EPOCH) << 22
        process_and_increment_bits = random.randrange(1 << 22)
        return nonce_timestamp | process_and_increment_bits

    async def __send_message(self, payload: dict, channelId: str):
        return await self.client.post(
            f"https://discord.com/api/v9/channels/{channelId}/messages", json=payload
        )

    async def __open_dm(self, userId: str):
        req = await self.client.post(
            "https://discord.com/api/v9/users/@me/channels",
            json={"recipients": [userId]},
        )
        if req.status_code != 200:
            console.f_print(f"{self.token} failed to open dm with {userId}")
            return None, req
        else:
            return req.json()["id"], req

    async def sendDirectMessage(self, userId: str, message: str):
        """Sends a direct message to <@userId>"""
        channelId, req = await self.__open_dm(userId)
        if channelId is None:
            return None, req  # do nothing if it failed to open dms with <@userId>
        payload = {"content": message, "tts": False, "nonce": self.__generate_nonce()}
        res = await self.__send_message(payload, channelId)
        if res.status_code == 200:
            return True, res
        else:
            return False, res

    async def sendMessageInChannel(
        self,
        message: str,
        channelId: str,
        massMention: bool = False,
        massMentionSize=6,
    ):
        scrappedMembers = open("scraped/massmention.txt").read().splitlines()
        if len(scrappedMembers) < 1 and massMention:
            console.f_print(
                f"{self.token} server has 0 members. thus mass mention wont work"
            )
            return False
        payload = {
            "flags": 0,
            "mobile_network_type": "unknown",
            "nonce": self.__generate_nonce(),
            "tts": False,
        }
        if massMention:
            # massMentionSize is either a fixed int or a (min, max) range — when it's a
            # range, roll a fresh size for every message so the mention count varies.
            if isinstance(massMentionSize, (tuple, list)):
                mentionCount = random.randint(massMentionSize[0], massMentionSize[1])
            else:
                mentionCount = massMentionSize
            mentions = "".join(
                f"<@{random.choice(scrappedMembers)}> " for _ in range(mentionCount)
            )
            randomChars = "".join(
                random.choice(string.ascii_letters + string.digits)
                for _ in range(random.randint(4, 8))
            )
            parts = [mentions.strip(), message, randomChars]
            random.shuffle(parts)
            payload["content"] = "\n".join(parts)
        else:
            payload["content"] = message
        req = await self.__send_message(payload, channelId)
        if req.status_code == 200:
            console.s_print(f"{self.token} successfully sent message in {channelId}")
            return True
        else:
            console.f_print(f"{self.token} failed to send message in {channelId}")
            return False

    async def checkToken(self):
        req = await self.client.get(
            "https://discord.com/api/v9/users/@me/affinities/guilds"
        )
        if req.status_code == 403:
            console.f_print(f"{self.token} is [LOCKED]")
            return False, "LOCKED"
        elif req.status_code == 401:
            console.f_print(
                f"{self.token} is {Fore.RESET}{Fore.YELLOW}[INVALID]{Fore.RESET}"
            )
            return False, "INVALID"
        else:
            console.s_print(f"{self.token} is [VALID]")
            return True, "VALID"

    async def getGuild(self, guildId: str):
        req = await self.client.get(f"https://discord.com/api/v9//guilds/{guildId}")
        if "name" not in req.json():
            console.f_print(f"{self.token} is probably not in {guildId}")
            return req.json()
        return req.json()

    async def getChannel(self, channelId):
        """Returns id of the server the channel is in"""
        req = await self.client.get(f"https://discord.com/api/v9/channels/{channelId}")
        if "guild_id" not in req.json():
            console.f_print(f"Server ID not found.")
            guildId = input(
                f"{Fore.GREEN}{Style.BRIGHT}Please enter the server Id: {Style.RESET_ALL}"
            )
            return guildId
        guildId = req.json()["guild_id"]
        if not guildId:
            return None
        return guildId

    async def leave(self, guildId: str):
        req = await self.client.delete(
            f"https://discord.com/api/v9/users/@me/guilds/{guildId}"
        )
        if req.status_code != 204:
            console.f_print(f"{self.token} failed to leave server: {guildId}")
            return False
        else:
            console.s_print(f"{self.token} left server: {guildId}")
            return True

    async def getMessage(self, messageId, channelId):
        """Gets the message, returns a message object 😃"""
        req = await self.client.get(
            f"https://discord.com/api/v9/channels/{channelId}/messages?limit=1&around={messageId}"
        )
        return req.json()

    async def getReactions(self, messageId, channelId):
        try:
            messageObject = (await self.getMessage(messageId, channelId))[0]
            reactions = list(messageObject["reactions"])
            if len(reactions) == 0:
                console.f_print("Message has 0 reactions.")
                return None
            return reactions[0]["emoji"]
        except Exception as e:
            console.f_print(e)
            return None

    async def getAllReactions(self, messageId, channelId):
        """Returns the full list of reaction objects on a message (each holds an
        `emoji` dict and a `count`), or None if the message has no reactions."""
        try:
            messageObject = (await self.getMessage(messageId, channelId))[0]
            reactions = list(messageObject["reactions"])
            if len(reactions) == 0:
                console.f_print("Message has 0 reactions.")
                return None
            return reactions
        except Exception as e:
            console.f_print(e)
            return None

    async def addReactionByEmoji(self, messageId, channelId, emojiObj):
        """Adds a single reaction to a message. `emojiObj` is the emoji dict taken
        from a reaction object: custom emojis carry an `id` and react as name:id,
        unicode emojis react as the url-encoded character."""
        if emojiObj.get("id"):
            emoji = f"{emojiObj['name']}%3A{emojiObj['id']}"
        else:
            emoji = quote(emojiObj["name"])
        try:
            req = await self.client.put(
                f"https://discord.com/api/v9/channels/{channelId}/messages/{messageId}"
                f"/reactions/{emoji}/%40me?location=Message&type=0"
            )
            if req.status_code != 204:
                console.f_print(f"{self.token} failed to add reaction.")
                return False
            console.s_print(f"{self.token} successfully added reaction.")
            return True
        except Exception as e:
            console.f_print(e)
            return False

    async def usernameChange(self, username: str, password: str):
        req = await self.client.patch(
            "https://discord.com/api/v9/users/@me",
            json={"password": password, "username": username},
        )
        if req.status_code == 200:
            console.s_print(f"{self.token} Username changed to {username}")
        else:
            console.f_print(f"{self.token} Failed to change username to {username}")

    async def bioChange(self, newBio: str):
        req = await self.client.patch(
            "https://discord.com/api/v9/users/@me", json={"bio": newBio}
        )
        if req.status_code != 200:
            console.f_print(f"{self.token} failed to change bio to {newBio}")
        else:
            console.s_print(f"{self.token} changed bio to {newBio}")

    def __detect_image_mime(self, data: bytes) -> str:
        """Sniffs the image type from its magic bytes (mirrors discord.py-self's
        _get_mime_type_for_image), so the data uri's mime matches the real bytes
        regardless of the url extension or CDN Content-Type. Falls back to png."""
        if data.startswith(b"\x89\x50\x4e\x47\x0d\x0a\x1a\x0a"):
            return "image/png"
        elif data[0:3] == b"\xff\xd8\xff" or data[6:10] in (b"JFIF", b"Exif"):
            return "image/jpeg"
        elif data.startswith((b"\x47\x49\x46\x38\x37\x61", b"\x47\x49\x46\x38\x39\x61")):
            return "image/gif"
        elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            return "image/webp"
        return "image/png"

    async def avatarChange(self, avatarUrl: str):
        """Downloads the image at avatarUrl, encodes it as a base64 data URI and
        PATCHes it onto the account avatar. Discord requires the md5 of the
        uploaded image echoed back in the X-Discord-Original-MD5 header, otherwise
        it rejects the change with 'Unknown Session' (code 10020)."""
        fetchUrl = avatarUrl.strip()
        if "cdn.discordapp.com" in fetchUrl and fetchUrl.endswith(".webp"):
            fetchUrl = fetchUrl[:-5] + ".png"
        downloader = AsyncClient(
            headers={"User-Agent": USER_AGENT},
            timeout=self._utility.config["requestTimeout"],
        )
        try:
            res = await downloader.get(fetchUrl)
        except Exception as e:
            console.f_print(f"{self.token} failed to download avatar: {e}")
            return False
        if res.status_code != 200:
            console.f_print(
                f"{self.token} failed to download avatar from {fetchUrl} [{res.status_code}]"
            )
            return False
        mime = self.__detect_image_mime(res.content)
        encoded = encoder(res.content).decode("ascii")
        dataUri = f"data:{mime};base64,{encoded}"
        imageMd5 = hashlib.md5(res.content).hexdigest()
        self.client.headers["X-Discord-Original-MD5"] = (
            f'user_default_profile_avatar="{imageMd5}"'
        )
        now = datetime.now()
        avatarDescription = f"images, added {now.day} {now.strftime('%B %Y at %H:%M')}"
        req = await self.client.patch(
            "https://discord.com/api/v9/users/@me",
            json={"avatar": dataUri, "avatar_description": avatarDescription},
        )
        self.client.headers.pop("X-Discord-Original-MD5", None)
        if req.status_code != 200:
            console.f_print(
                f"{self.token} failed to change avatar [{req.status_code}]: {req.text}"
            )
            return False
        console.s_print(f"{self.token} changed avatar")
        return True

    async def sendFriendRequest(self, username, discrim):
        req = await self.client.post(
            "https://discord.com/api/v9/users/@me/relationships",
            json={"username": username, "discriminator": discrim},
        )
        if req.status_code != 204:
            console.f_print(
                f"{self.token} Failed to send friend request to {username}#{discrim}"
            )
            return req
        else:
            console.s_print(f"{self.token} Sent friend request to {username}#{discrim}")
            return req
