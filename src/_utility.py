import random, json, re
from httpz import Client
from colorama import Fore, Style
from base64 import b64encode as b
import httpz


class Utility:
    def __init__(self):
        self.config = self.getConfig()
        self.proxy = self.getProxy()

    def getConfig(self):
        return json.loads(open("config.json").read())

    def getProxy(self):
        if self.config["proxy"]["proxyless"]:
            return None
        return f"{self.config['proxy']['protocol']}://{random.choice(open('input/proxies.txt').read().splitlines())}"

    def getBuildNum(self):
        """Gets the build number that discord is currently on, makes the x-super-properties header more realistic."""
        try:
            client = Client(impersonate="chrome148", timeout=30)
            page = client.get("https://discord.com/login").text
            assets = re.compile(
                r'<script defer src="/assets/((?:[a-zA-Z0-9]+\.)?[a-zA-Z0-9]+\.js)',
                re.I,
            ).findall(page)
            for asset in reversed(assets):
                body = client.get(f"https://discord.com/assets/{asset}").text.replace(
                    " ", ""
                )
                if 'buildNumber:"' not in body:
                    continue
                return body.split('buildNumber:"')[1].split('"')[0]
        except Exception:
            pass
        return "555975"

    def getContextProperties(self, guildId: str, channelId: str) -> str:
        return b(
            json.dumps(
                {
                    "location": "Join Guild",
                    "location_guild_id": guildId,
                    "location_channel_id": channelId,
                    "location_channel_type": 0,
                },
                separators=(",", ":"),
            ).encode()
        ).decode()

    def getInviteInfo(self, rawInvite):
        res = httpz.get(
            f"https://discord.com/api/v9/invites/{rawInvite}?with_counts=true",
            headers={"Authorization": "undefined"},
            timeout=30,
        ).json()
        return res


class MPrint:
    def w_print(self, message: str):
        """Print warning"""
        print(
            f"[{Style.BRIGHT}{Fore.RED}WARN{Style.RESET_ALL}] {Style.BRIGHT}{Fore.YELLOW}{message}{Style.RESET_ALL}"
        )

    def s_print(self, message: str):
        """Print SUCCESS"""
        print(
            f"[{Style.BRIGHT}{Fore.MAGENTA}SUCCESS{Style.RESET_ALL}] {Style.BRIGHT}{Fore.GREEN}{message}{Style.RESET_ALL}"
        )

    def f_print(self, message: str):
        """Print FAIL"""
        print(
            f"[{Style.BRIGHT}{Fore.YELLOW}FAILED{Style.RESET_ALL}] {Style.BRIGHT}{Fore.RED}{message}{Style.RESET_ALL}"
        )


console = MPrint()

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:151.0) Gecko/20100101 Firefox/151.0"
)

BUILD_NUM = Utility().getBuildNum()


def gatewayProperties() -> dict:
    """Classic gateway IDENTIFY `properties`, kept in lockstep with the HTTP
    super-properties identity (Windows / Firefox 151) so the two layers agree."""
    return {
        "os": "Windows",
        "browser": "Firefox",
        "device": "",
        "system_locale": "en-US",
        "browser_user_agent": USER_AGENT,
        "browser_version": "151.0",
        "os_version": "10",
        "referrer": "",
        "referring_domain": "",
        "referrer_current": "",
        "referring_domain_current": "",
        "release_channel": "stable",
        "client_build_number": int(BUILD_NUM),
        "client_event_source": None,
    }
