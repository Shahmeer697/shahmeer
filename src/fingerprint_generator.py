# Generates X-Fingerprints at high throughput and saves them by date
# @author Shahzain345

import os
import signal
import asyncio
from datetime import datetime

from curl_cffi.requests import AsyncSession
from ._trackers import AntiTracking
from ._utility import Utility, MPrint, BUILD_NUM

console = MPrint()

EXPERIMENTS_URL = "https://discord.com/api/v9/experiments"

# Windows' select() (used by curl_cffi's selector thread) can only watch 512 file
# descriptors, so the number of *concurrent* sockets must stay well under that.
# We keep headroom for stdio/files/DNS. IP diversity comes from rotating every
# request across the whole proxy list, not from holding 1000 sockets open at once.
MAX_SAFE_CONCURRENCY = 450


class FpScrapper:
    """
    High-throughput X-Fingerprint generator.

    Discord rate-limits GET /api/v9/experiments PER IP — a single IP yields only a
    few hundred fingerprints before it gets pinned at 429. Real throughput comes
    from spreading requests across many IPs, so every request is sent through the
    NEXT proxy in the list (round-robin). With a rotating-gateway proxy list that
    means a different exit IP per request, i.e. every IP is its own rate-limit
    bucket and the buckets are filled in parallel.

    Concurrency is capped (MAX_SAFE_CONCURRENCY) because Windows' select() can't
    watch more than 512 sockets at once — going over that is what throws
    "too many file descriptors in select()". All requests share ONE curl_cffi
    AsyncSession with a real Firefox TLS/HTTP2 fingerprint (impersonate="firefox").

    Fingerprints are pushed onto an in-memory queue and flushed to disk in batches
    by ONE writer task, keeping slow disk I/O off the request hot path.
    """

    def __init__(
        self,
        max_concurrent: int = 400,
        direct_workers: int = 50,
        flush_every: int = 1000,
    ):
        self._utility = Utility()
        self._anti_tracking = AntiTracking(BUILD_NUM)
        self.max_concurrent = min(max_concurrent, MAX_SAFE_CONCURRENCY)
        self.direct_workers = min(direct_workers, MAX_SAFE_CONCURRENCY)
        self.flush_every = flush_every

        self.count = 0
        self.proxies: list = []
        self._proxy_idx = 0
        self._queue: asyncio.Queue = asyncio.Queue()
        self._stop = asyncio.Event()
        self.session: AsyncSession = None

    def _load_proxies(self) -> list:
        """Read input/proxies.txt and turn each line into a full proxy url. Empty
        when proxyless is on or the file is missing."""
        cfg = self._utility.config
        if cfg["proxy"]["proxyless"]:
            return []
        try:
            lines = [
                l.strip()
                for l in open("input/proxies.txt").read().splitlines()
                if l.strip()
            ]
        except FileNotFoundError:
            return []
        protocol = cfg["proxy"]["protocol"]
        return [f"{protocol}://{l}" for l in lines]

    def _next_proxy(self):
        """Round-robin the proxy list (single-threaded asyncio, no lock needed)."""
        if not self.proxies:
            return None
        proxy = self.proxies[self._proxy_idx % len(self.proxies)]
        self._proxy_idx += 1
        return proxy

    def _build_session(self) -> AsyncSession:
        return AsyncSession(
            impersonate="firefox",
            max_clients=self.max_concurrent + 16,
            timeout=self._utility.config["requestTimeout"],
            headers={
                "Accept": "*/*",
                "Accept-Language": f"{self._anti_tracking.lang},en;q=0.9",
                "X-Super-Properties": self._anti_tracking.super_props,
            },
        )

    def _filename(self) -> str:
        """./scraped/fingerprints/fps-{day-month-year}.txt (created on demand)."""
        directory = "./scraped/fingerprints"
        os.makedirs(directory, exist_ok=True)
        return f"{directory}/fps-{datetime.now().strftime('%d-%m-%Y')}.txt"

    async def _worker(self):
        """Tight request loop. Each request goes through the next proxy in the
        rotation so we cycle every IP over time. 429s/errors are skipped so the
        loop never stalls."""
        session = self.session
        queue = self._queue
        while not self._stop.is_set():
            try:
                proxy = self._next_proxy()
                kwargs = {"proxies": {"http": proxy, "https": proxy}} if proxy else {}
                resp = await session.get(EXPERIMENTS_URL, **kwargs)
                if resp.status_code != 200:
                    continue
                fp = resp.json().get("fingerprint")
                if not fp:
                    continue
                self.count += 1
                queue.put_nowait(fp)
                console.s_print(f"Generated fingerprint: {fp}")
            except Exception:
                continue

    async def _writer(self):
        """Single batched writer: drains the queue and appends in big chunks so
        we do one open()/write() per `flush_every` fingerprints, not per fp."""
        buffer = []
        while not (self._stop.is_set() and self._queue.empty()):
            try:
                buffer.append(await asyncio.wait_for(self._queue.get(), timeout=1))
            except asyncio.TimeoutError:
                pass
            if buffer and (len(buffer) >= self.flush_every or self._queue.empty()):
                with open(self._filename(), "a", encoding="utf-8") as f:
                    f.write("\n".join(buffer) + "\n")
                buffer.clear()

    async def generate_fps(self):
        """Spin up the bounded worker pool + writer and run until cancelled."""
        self.proxies = self._load_proxies()
        if self.proxies:
            num_workers = self.max_concurrent
            console.s_print(
                f"Loaded {len(self.proxies)} proxies -> {num_workers} concurrent workers "
                f"(rotating every request across all proxies)"
            )
        else:
            num_workers = self.direct_workers
            console.w_print(
                "Proxyless: Discord rate-limits /experiments per IP, so you'll get "
                "a few hundred fingerprints then mostly 429s. Add proxies to "
                "input/proxies.txt to scale."
            )

        self.session = self._build_session()
        writer = asyncio.create_task(self._writer())
        workers = [asyncio.create_task(self._worker()) for _ in range(num_workers)]

        # Ctrl+C can't reliably raise KeyboardInterrupt while 400 workers saturate
        # the loop, so handle SIGINT directly: just flip the stop event. We restore
        # the previous handler on the way out so the menu behaves normally after.
        previous_handler = None
        try:
            previous_handler = signal.getsignal(signal.SIGINT)
            signal.signal(signal.SIGINT, lambda *_: self._stop.set())
        except (ValueError, OSError):
            previous_handler = None

        try:
            await self._stop.wait()  # blocks here until Ctrl+C flips the event
        finally:
            self._stop.set()
            for w in workers:
                w.cancel()
            await writer
            try:
                await self.session.close()
            except Exception:
                pass
            if previous_handler is not None:
                try:
                    signal.signal(signal.SIGINT, previous_handler)
                except (ValueError, OSError):
                    pass
            console.s_print(f"Stopped. Total fingerprints generated: {self.count}")
