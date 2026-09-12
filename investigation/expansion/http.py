"""HTTP educado: robots.txt, opt-out de IA, rate limit por host, retry.

Politica:
  - respeita `robots.txt` (urllib.robotparser) e o crawl-delay quando declarado;
  - detecta opt-out de robos de treino de IA (GPTBot, ClaudeBot, CCBot,
    Google-Extended, Bytespider, Amazonbot, Applebot-Extended, meta-externalagent)
    e marca o host como proibido para conteudo;
  - 1 requisicao por segundo por host (ou crawl-delay);
  - retry/backoff exponencial em 429/5xx respeitando `Retry-After`;
  - timeout configuravel; thread-safe.
"""
from __future__ import annotations

import threading
import time
import urllib.robotparser
from dataclasses import dataclass, field
from urllib.parse import urlparse

import requests

UA = "FakenewsBR-research/2.0 (+https://github.com/thiago-cg/FakenewsBR; research)"
AI_BOTS = (
    "GPTBot", "ClaudeBot", "anthropic-ai", "CCBot", "Google-Extended",
    "Bytespider", "Amazonbot", "Applebot-Extended", "meta-externalagent",
    "FacebookBot", "PerplexityBot", "cohere-ai", "Omgilibot",
)
DEFAULT_DELAY = 1.0
TIMEOUT = 30


@dataclass
class HostState:
    last_request: float = 0.0
    delay: float = DEFAULT_DELAY
    robot: urllib.robotparser.RobotFileParser | None = None
    ai_optout: bool = False
    robots_loaded: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)


class PoliteSession:
    def __init__(self, user_agent: str = UA, delay: float = DEFAULT_DELAY,
                 timeout: int = TIMEOUT, respect_robots: bool = True,
                 block_ai_optout: bool = True):
        self.ua = user_agent
        self.delay = delay
        self.timeout = timeout
        self.respect_robots = respect_robots
        self.block_ai_optout = block_ai_optout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self._hosts: dict[str, HostState] = {}
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- estado
    def _state(self, host: str) -> HostState:
        with self._lock:
            if host not in self._hosts:
                self._hosts[host] = HostState()
            return self._hosts[host]

    def _load_robots(self, scheme: str, host: str, st: HostState) -> None:
        if st.robots_loaded:
            return
        st.robots_loaded = True
        rp = urllib.robotparser.RobotFileParser()
        robots_url = f"{scheme}://{host}/robots.txt"
        try:
            r = self.session.get(robots_url, timeout=self.timeout)
        except requests.RequestException:
            st.robot = None
            return
        if r.status_code >= 400:
            st.robot = None
            return
        rp.parse(r.text.splitlines())
        st.robot = rp
        # crawl-delay
        cd = None
        try:
            cd = rp.crawl_delay(self.ua) or rp.crawl_delay("*")
        except Exception:
            cd = None
        if cd:
            try:
                st.delay = max(self.delay, float(cd))
            except (TypeError, ValueError):
                pass
        # opt-out de IA: se um bot de treino listado esta bloqueado em /
        if self.block_ai_optout:
            for bot in AI_BOTS:
                try:
                    if not rp.can_fetch(bot, f"{scheme}://{host}/"):
                        st.ai_optout = True
                        break
                except Exception:
                    continue

    def allows(self, url: str) -> tuple[bool, str]:
        """(permitido, motivo). Motivo vazio quando permitido."""
        if not self.respect_robots:
            return True, ""
        p = urlparse(url)
        host = p.netloc
        st = self._state(host)
        if not st.robots_loaded:
            self._load_robots(p.scheme or "https", host, st)
        if st.ai_optout and self.block_ai_optout:
            return False, "ai_optout"
        if st.robot is not None and not st.robot.can_fetch(self.ua, url):
            return False, "robots_disallow"
        return True, ""

    def is_ai_optout(self, url: str) -> bool:
        p = urlparse(url)
        st = self._state(p.netloc)
        if not st.robots_loaded:
            self._load_robots(p.scheme or "https", p.netloc, st)
        return st.ai_optout

    # ---------------------------------------------------------------- get
    def _throttle(self, host: str) -> None:
        st = self._state(host)
        with st.lock:
            now = time.monotonic()
            wait = st.delay - (now - st.last_request)
            if wait > 0:
                time.sleep(wait)
            st.last_request = time.monotonic()

    def get(self, url: str, *, params=None, headers=None, max_retries: int = 4,
            allow_fetch: bool = True, **kw):
        """GET educado. Retorna `requests.Response` ou None se bloqueado/falhou."""
        if allow_fetch:
            ok, why = self.allows(url)
            if not ok:
                return None
        host = urlparse(url).netloc
        last_exc: Exception | None = None
        for attempt in range(max_retries):
            self._throttle(host)
            try:
                r = self.session.get(url, params=params, headers=headers,
                                     timeout=self.timeout, **kw)
            except requests.RequestException as e:
                last_exc = e
                time.sleep(min(2 ** attempt, 30))
                continue
            if r.status_code == 429 or 500 <= r.status_code < 600:
                ra = r.headers.get("Retry-After")
                try:
                    back = float(ra) if ra else min(2 ** attempt, 60)
                except ValueError:
                    back = min(2 ** attempt, 60)
                time.sleep(min(back, 120))
                continue
            return r
        if last_exc:
            return None
        return r

    def get_json(self, url: str, **kw):
        r = self.get(url, **kw)
        if r is None or r.status_code != 200:
            return None, (r.status_code if r is not None else None)
        try:
            return r.json(), 200
        except ValueError:
            return None, "json_error"
