# Changelog

## 0.2.0 (2026-11-13)

- Fix: refused connections and timeouts through the proxy are now retried from a new IP. The middleware listed Python's built-in `ConnectionRefusedError`, but Scrapy raises Twisted's own classes, and recent Scrapy versions wrap them again (`DownloadConnectionRefusedError`, `DownloadTimeoutError`, `DownloadFailedError`, `ResponseDataLossError`). Before, only dropped connections and tunnel errors got a new IP.
- Tests: unit tests for every setting and an end-to-end crawl through a local proxy that refuses or drops connections.
- Package metadata for PyPI.

## 0.1.0 (2026-11-12)

- First release: country targeting, sticky session per site or key, new IP on 403/429, captcha pages and dropped connections, stats.
