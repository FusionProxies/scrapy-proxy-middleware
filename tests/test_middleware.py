import base64
from urllib.parse import unquote, urlparse

import pytest
from scrapy import Request
from scrapy.downloadermiddlewares.httpproxy import HttpProxyMiddleware
from scrapy.exceptions import NotConfigured
from scrapy.http import HtmlResponse
from scrapy.utils.test import get_crawler
from scrapy.core.downloader.handlers.http11 import TunnelError
from twisted.internet.error import ConnectionRefusedError, DNSLookupError, TCPTimedOutError

from scrapy_fusionproxy import FusionProxyMiddleware

BASE = {"FUSIONPROXY_USER": "user123", "FUSIONPROXY_PASS": "p@ss:word"}


def make(**settings):
    crawler = get_crawler(settings_dict={**BASE, **settings})
    return FusionProxyMiddleware.from_crawler(crawler), crawler


def proxied(mw, url, **meta):
    req = Request(url, meta=meta)
    assert mw.process_request(req) is None
    return req


def username(req):
    return unquote(urlparse(req.meta["proxy"]).username)


def test_missing_credentials(monkeypatch):
    monkeypatch.delenv("FUSION_USER", raising=False)
    monkeypatch.delenv("FUSION_PASS", raising=False)
    with pytest.raises(NotConfigured):
        FusionProxyMiddleware.from_crawler(get_crawler(settings_dict={}))


def test_credentials_from_environment(monkeypatch):
    monkeypatch.setenv("FUSION_USER", "envuser")
    monkeypatch.setenv("FUSION_PASS", "envpass")
    mw = FusionProxyMiddleware.from_crawler(get_crawler(settings_dict={}))
    assert username(proxied(mw, "https://example.com/")).startswith("envuser-sessid-")


def test_proxy_url_country_and_sticky_session():
    mw, _ = make(FUSIONPROXY_COUNTRY="US", FUSIONPROXY_STICKY_MINUTES=5)
    req = proxied(mw, "https://example.com/a")
    u = urlparse(req.meta["proxy"])
    assert (u.scheme, u.hostname, u.port) == ("http", "resi.fusionproxy.net", 12286)
    assert unquote(u.password) == "p@ss:word"
    name = username(req)
    assert name.startswith("user123-country-us-sessid-") and name.endswith("-sessTime-300s")


def test_one_ip_per_site_and_per_session_key():
    mw, _ = make()
    a1, a2 = username(proxied(mw, "https://a.example/1")), username(proxied(mw, "https://a.example/2"))
    b = username(proxied(mw, "https://b.example/1"))
    assert a1 == a2 and a1 != b
    k = username(proxied(mw, "https://a.example/3", fusion_session="account-7"))
    assert k != a1


def test_rotating_mode_and_per_request_country():
    mw, _ = make(FUSIONPROXY_STICKY_MINUTES=0, FUSIONPROXY_COUNTRY="us")
    assert username(proxied(mw, "https://example.com/")) == "user123-country-us"
    assert username(proxied(mw, "https://example.com/", fusion_country="DE")) == "user123-country-de"


def test_skip_proxy():
    mw, _ = make()
    req = proxied(mw, "https://example.com/", fusion_proxy=False)
    assert "proxy" not in req.meta
    resp = HtmlResponse(req.url, status=403, request=req)
    assert mw.process_response(req, resp) is resp


def test_block_moves_site_to_new_ip_then_gives_up():
    mw, crawler = make(FUSIONPROXY_MAX_ROTATIONS=2)
    req = proxied(mw, "https://shop.example/item")
    first = username(req)
    retry = mw.process_response(req, HtmlResponse(req.url, status=429, request=req))
    assert isinstance(retry, Request) and retry.dont_filter and retry.meta["fusion_rotations"] == 1
    mw.process_request(retry)
    assert username(retry) != first
    retry2 = mw.process_response(retry, HtmlResponse(retry.url, status=403, request=retry))
    mw.process_request(retry2)
    final = HtmlResponse(retry2.url, status=403, request=retry2)
    assert mw.process_response(retry2, final) is final  # third block: give up, pass the response on
    stats = crawler.stats.get_stats()
    assert stats["fusionproxy/rotations"] == 2 and stats["fusionproxy/gave_up"] == 1
    assert stats["fusionproxy/banned/429"] == 1 and stats["fusionproxy/banned/403"] == 2


def test_captcha_page_counts_as_block_but_normal_page_does_not():
    mw, _ = make()
    req = proxied(mw, "https://example.com/")
    captcha = HtmlResponse(req.url, status=200, body=b"<h1>Please solve the CAPTCHA</h1>", request=req)
    assert isinstance(mw.process_response(req, captcha), Request)
    ok = HtmlResponse(req.url, status=200, body=b"<h1>Products</h1>", request=req)
    assert mw.process_response(req, ok) is ok


def test_connection_errors_retry_from_new_ip_others_are_left_alone():
    mw, _ = make()
    req = proxied(mw, "https://example.com/")
    for exc in (ConnectionRefusedError(), TCPTimedOutError(), TunnelError("Could not open CONNECT tunnel")):
        assert isinstance(mw.process_exception(req, exc), Request), exc
    assert mw.process_exception(req, DNSLookupError()) is None  # the target does not exist: a new IP will not help
    assert mw.process_exception(req, ValueError("bug")) is None


def test_works_with_scrapy_httpproxy_middleware():
    """Scrapy's own HttpProxyMiddleware (priority 750) turns the URL credentials into the header."""
    mw, crawler = make()
    req = proxied(mw, "https://example.com/")
    expected = username(req)
    HttpProxyMiddleware.from_crawler(crawler).process_request(req)
    auth = req.headers[b"Proxy-Authorization"].decode()
    user, password = base64.b64decode(auth.split()[1]).decode().split(":", 1)
    assert user == expected and password == "p@ss:word"
    assert urlparse(req.meta["proxy"]).hostname == "resi.fusionproxy.net"
