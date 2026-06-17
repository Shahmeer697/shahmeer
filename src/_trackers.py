import random
import uuid
import json

from difflib import SequenceMatcher
from base64 import b64encode


_FIREFOX151_FP: dict = {
    "browser": "firefox",
    "h2_fingerprint": "1:65536;2:0;4:131072;5:16384|12517377|0|m,p,a,s",
    "h2_fingerprint_hash": "6ea73faa8fc5aac76bded7bd238f6433",
    "ja3": "771,4865-4867-4866-49195-49199-52393-52392-49196-49200-49162-49171-49172-156-157-47-53,0-23-65281-10-11-16-5-34-18-51-43-13-45-28-27-65037,4588-29-23-24-25-256-257,0",
    "ja3_hash": "8acff3e590a96b13277b940a3aa0e9a9",
    "source": "manual",
    "source_name": "firefox151",
    "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:151.0) Gecko/20100101 Firefox/151.0",
}



class AntiTracking:
    """
    Wears a fresh disguise on every request. This class forges believable Firefox
    user-agents and pairs them with matching JA3 and Akamai fingerprints, so each
    connection looks like a real browser instead of a bot — slipping past Discord's
    HTTP fingerprinting checks.
    """
    def __init__(self, build_num: int) -> None:
        self._build_num = build_num
        self._launch_id = str(uuid.uuid4())
        self._launch_signature = str(uuid.uuid4())
        self._heartbeat_session_id = str(uuid.uuid4())
        self.ua, self.browser_version, self.os_version = self._generate_firefox_useragent()
        self.lang = random.choice(["en-GB", "en-US", "en-PK"])
        tls_data = self._generate_similar_ja3_and_h2(min_similarity=0.85)
        self.akamai, self.ja3 = tls_data["h2_fingerprint"], tls_data["ja3"]
        self._super_properties_dict = self._super_properties()
        self.super_props = b64encode(
            json.dumps(self._super_properties_dict, separators=(",", ":")).encode()
        ).decode()
        self.timezone = self._generate_timezone()
    def _super_properties(self, session_id: str = None) -> dict:
        """Build the Firefox 151 (Windows) x-super-properties payload.

        Mirrors a real Firefox client's tracker: Windows/Firefox identity,
        and the live build number. Built once so
        the encoded header and the returned dict share the same per-launch UUIDs.
        """
        props = {
            "os": "Windows",
            "browser": "Firefox",
            "device": "",
            "system_locale": self.lang,
            "has_client_mods": False,
            "browser_user_agent": self.ua,
            "browser_version": self.browser_version,
            "os_version": self.os_version,
            "referrer": "",
            "referring_domain": "",
            "search_engine": "google",
            "referrer_current": "https://discord.com/",
            "referring_domain_current": "discord.com",
            "release_channel": "stable",
            "client_build_number": self._build_num,
            "client_event_source": None,
            "client_launch_id": self._launch_id,
        }
        if session_id is not None:
            props["client_heartbeat_session_id"] = session_id
        props["launch_signature"] = self._launch_signature
        props["client_app_state"] = "focused"
        return props
    def _generate_firefox_useragent(self):
        """Mint a random Windows Firefox User-Agent string.

        Rolls a version number somewhere in the 134->151 range so the UA stays in step
        with the firefoxX TLS/H2 fingerprint this multitool hands out (see
        ``generate_similar_ja3_and_h2``) - if the advertised browser and the actual JA3
        don't agree, that contradiction alone gives the bot away. Hands back
        ``(user_agent, browser_version, os_version)`` to match the shape of
        ``generate_safari_useragent``.
        """
        browser_version = random.randint(134, 151)
        os_version = "10"
        user_agent = (
            f"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:{browser_version}.0) "
            f"Gecko/20100101 Firefox/{browser_version}"
        )
        return user_agent, browser_version, os_version

    def _generate_timezone(self) -> str:
        """Pick a random IANA timezone for the X-Discord-Timezone header.

        Every account reporting the exact same timezone is a cheap correlation
        signal, so each launch draws one at random from a pool of busy,
        real-world zones. For the cleanest disguise the chosen zone should line
        up with the region your proxy exits from.
        """
        timezones = [
            "America/New_York",
            "America/Chicago",
            "America/Denver",
            "America/Los_Angeles",
            "America/Sao_Paulo",
            "Europe/London",
            "Europe/Paris",
            "Europe/Berlin",
            "Europe/Madrid",
            "Europe/Moscow",
            "Asia/Dubai",
            "Asia/Karachi",
            "Asia/Kolkata",
            "Asia/Singapore",
            "Asia/Tokyo",
            "Australia/Sydney",
        ]
        return random.choice(timezones)

    def _generate_similar_ja3_and_h2(self,
        base_fp: dict = _FIREFOX151_FP, min_similarity: float = 0.80
        ) -> dict:
        """Return a copy of ``base_fp`` whose JA3 + Akamai/H2 fingerprint is at least
        ``min_similarity`` similar to the original but NOT identical.

        A real Firefox build always sends the same TLS/H2 handshake, so a fleet of
        accounts that all reuse one captured fingerprint share a single ja3_hash /
        h2_fingerprint_hash - a trivial correlation signal. This perturbs ONLY the
        parts a TLS/H2 stack can legitimately vary without changing what the browser
        can do, so every account still reads as the same Firefox with a slightly
        different-but-plausible handshake:

        * JA3  - keep the TLS version, cipher list and EC point formats (these carry
                the browser's identity); reorder the TLS extensions and the
                supported-groups tail (order is negotiable; the *set* is unchanged).
        * H2   - keep the SETTINGS values + order and the pseudo-header order (Firefox
                identity); jitter only the connection WINDOW_UPDATE increment.

        Both hashes are recomputed (MD5 of the new string, same as the originals).
        Similarity is measured per field with difflib so each lands in
        ``[min_similarity, 1.0)``.
        """
        ver, ciphers, exts, curves, pfmt = base_fp["ja3"].split(",")
        ext_list = [e for e in exts.split("-") if e != "41"]
        curve_list = curves.split("-")

        def _make_ja3() -> str:
            e = ext_list[:]
            random.shuffle(e)
            c = curve_list[:]
            if len(c) > 2:
                tail = c[1:]
                random.shuffle(tail)
                c = c[:1] + tail
            return ",".join([ver, ciphers, "-".join(e), "-".join(c), pfmt])

        new_ja3 = base_fp["ja3"]
        for _ in range(300):
            cand = _make_ja3()
            if (
                cand != base_fp["ja3"]
                and SequenceMatcher(None, cand, base_fp["ja3"]).ratio() >= min_similarity
            ):
                new_ja3 = cand
                break
        if new_ja3 == base_fp["ja3"] and len(ext_list) >= 2:
            e = ext_list[:]
            i = random.randrange(len(e) - 1)
            e[i], e[i + 1] = e[i + 1], e[i]
            new_ja3 = ",".join([ver, ciphers, "-".join(e), curves, pfmt])

        settings, window, prio, horder = base_fp["h2_fingerprint"].split("|")
        new_h2 = base_fp["h2_fingerprint"]
        try:
            w = int(window)
            span = max(1, w // 20)
            for _ in range(300):
                cand_w = w + random.randint(-span, span)
                cand = "|".join([settings, str(cand_w), prio, horder])
                if (
                    cand != base_fp["h2_fingerprint"]
                    and SequenceMatcher(None, cand, base_fp["h2_fingerprint"]).ratio()
                    >= min_similarity
                ):
                    new_h2 = cand
                    break
        except ValueError:
            pass

        out = dict(base_fp)
        out["ja3"] = new_ja3
        out["h2_fingerprint"] = new_h2
        out["source"] = "generated"
        return out