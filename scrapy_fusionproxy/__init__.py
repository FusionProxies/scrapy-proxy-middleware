"""Scrapy downloader middleware for rotating residential proxies.

- sends every request through the proxy gateway with country targeting
- optional sticky sessions: one residential IP per website (or per key you choose)
- when a site blocks (403, 429, captcha page) or the connection drops, it moves that
  website to a new IP and retries the request

Settings (settings.py):

    DOWNLOADER_MIDDLEWARES = {"scrapy_fusionproxy.FusionProxyMiddleware": 610}
    FUSIONPROXY_USER = "your_username"          # or the FUSION_USER environment variable
    FUSIONPROXY_PASS = "your_password"          # or FUSION_PASS
    FUSIONPROXY_COUNTRY = "us"                  # optional, two-letter code
    FUSIONPROXY_STICKY_MINUTES = 10             # 0 = new IP on every connection
    FUSIONPROXY_BAN_CODES = [403, 429]
    FUSIONPROXY_MAX_ROTATIONS = 3               # new IPs to try per request after a block

Per request (request.meta):

    "fusion_country": "de"      override the country
    "fusion_session": "cart-1"  sticky key (default: the website's host name)
    "fusion_proxy": False       skip the proxy for this request
"""
import logging
import os
import random
from urllib.parse import quote, urlparse

from scrapy.core.downloader.handlers.http11 import TunnelError
from scrapy.exceptions import NotConfigured
from twisted.internet.error import ConnectionLost, TCPTimedOutError, TimeoutError as TxTimeoutError
from twisted.web._newclient import ResponseNeverReceived

__all__ = ["FusionProxyMiddleware"]
__version__ = "0.1.0"

NETWORK_ERRORS = (TunnelError, ConnectionLost, TCPTimedOutError, TxTimeoutError, ResponseNeverReceived, ConnectionRefusedError)


class FusionProxyMiddleware:
    def __init__(self, settings, stats, crawler=None):
        self.crawler = crawler
        self.user = settings.get("FUSIONPROXY_USER") or os.environ.get("FUSION_USER")
        self.password = settings.get("FUSIONPROXY_PASS") or os.environ.get("FUSION_PASS")
        if not self.user or not self.password:
            raise NotConfigured("set FUSIONPROXY_USER and FUSIONPROXY_PASS (or FUSION_USER and FUSION_PASS)")
        self.host = settings.get("FUSIONPROXY_HOST", "resi.fusionproxy.net")
        self.port = settings.getint("FUSIONPROXY_PORT", 12286)
        self.country = settings.get("FUSIONPROXY_COUNTRY") or os.environ.get("FUSION_COUNTRY") or ""
        self.sticky_minutes = settings.getint("FUSIONPROXY_STICKY_MINUTES", 10)
        self.ban_codes = set(settings.getlist("FUSIONPROXY_BAN_CODES", [403, 429]))
        self.ban_markers = [m.lower().encode() for m in settings.getlist("FUSIONPROXY_BAN_TEXT", ["captcha", "access denied"])]
        self.max_rotations = settings.getint("FUSIONPROXY_MAX_ROTATIONS", 3)
        self.stats = stats
        self.sessions = {}  # sticky key -> session id

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings, crawler.stats, crawler)

    # --- helpers -----------------------------------------------------------------

    def _key(self, request):
        return request.meta.get("fusion_session") or urlparse(request.url).hostname or ""

    def _rotate(self, key):
        self.sessions[key] = random.randint(1000000, 9999999)
        self.stats.inc_value("fusionproxy/rotations")

    def _username(self, request):
        name = self.user
        country = request.meta.get("fusion_country", self.country)
        if country:
            name += f"-country-{country.lower()}"
        if self.sticky_minutes > 0:
            key = self._key(request)
            if key not in self.sessions:
                self.sessions[key] = random.randint(1000000, 9999999)
            name += f"-sessid-{self.sessions[key]}-sessTime-{self.sticky_minutes * 60}s"
        return name

    @property
    def _log(self):
        spider = getattr(self.crawler, "spider", None)
        return spider.logger if spider else logging.getLogger(__name__)

    def _retry(self, request, reason):
        tries = request.meta.get("fusion_rotations", 0)
        if tries >= self.max_rotations:
            self.stats.inc_value("fusionproxy/gave_up")
            self._log.warning("fusionproxy: giving up on %s after %d new IPs (%s)", request.url, tries, reason)
            return None
        self._rotate(self._key(request))
        self._log.info("fusionproxy: %s on %s, retrying from a new IP", reason, request.url)
        retry = request.copy()
        retry.meta["fusion_rotations"] = tries + 1
        retry.dont_filter = True
        return retry

    # --- Scrapy hooks --------------------------------------------------------------

    def process_request(self, request, spider=None):
        if request.meta.get("fusion_proxy") is False:
            return None
        user = quote(self._username(request), safe="")
        # credentials in the proxy URL; Scrapy's HttpProxyMiddleware (priority 750)
        # turns them into the Proxy-Authorization header
        request.meta["proxy"] = f"http://{user}:{quote(self.password, safe='')}@{self.host}:{self.port}"
        self.stats.inc_value("fusionproxy/requests")
        return None

    def process_response(self, request, response, spider=None):
        if request.meta.get("fusion_proxy") is False:
            return response
        banned = response.status in self.ban_codes
        if not banned and response.status == 200 and len(response.body) < 20000:
            body = response.body.lower()
            banned = any(m in body for m in self.ban_markers)
        if banned:
            self.stats.inc_value(f"fusionproxy/banned/{response.status}")
            retry = self._retry(request, f"HTTP {response.status}")
            if retry is not None:
                return retry
        return response

    def process_exception(self, request, exception, spider=None):
        if request.meta.get("fusion_proxy") is False or not isinstance(exception, NETWORK_ERRORS):
            return None
        self.stats.inc_value("fusionproxy/connection_errors")
        return self._retry(request, type(exception).__name__)
