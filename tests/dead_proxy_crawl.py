"""Run a real Scrapy crawl through a local proxy that refuses or drops every
connection, then print the crawl stats as JSON. Used by test_crawl.py in a
separate process, because the Twisted reactor cannot be restarted."""
import json
import socket
import sys
import threading

import scrapy
from scrapy.crawler import CrawlerProcess

mode = sys.argv[1]  # "refused" or "drop"
if mode == "refused":
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()  # nothing listens there
else:
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(50)
    port = srv.getsockname()[1]

    def drop_all():
        while True:
            c, _ = srv.accept()
            c.recv(4096)
            c.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, b"\x01\x00\x00\x00\x00\x00\x00\x00")
            c.close()  # reset: the connection is lost mid-request

    threading.Thread(target=drop_all, daemon=True).start()


class OnePage(scrapy.Spider):
    name = "one_page"
    start_urls = ["https://example.com/"]

    def parse(self, response):
        pass


process = CrawlerProcess(settings={
    "DOWNLOADER_MIDDLEWARES": {"scrapy_fusionproxy.FusionProxyMiddleware": 610},
    "FUSIONPROXY_USER": "user", "FUSIONPROXY_PASS": "pass",
    "FUSIONPROXY_HOST": "127.0.0.1", "FUSIONPROXY_PORT": port, "FUSIONPROXY_MAX_ROTATIONS": 2,
    "RETRY_ENABLED": False, "LOG_LEVEL": "CRITICAL", "MEMUSAGE_ENABLED": False,
    "TELNETCONSOLE_ENABLED": False, "DOWNLOAD_TIMEOUT": 5,
})
crawler = process.create_crawler(OnePage)
process.crawl(crawler)
process.start()
print(json.dumps({k: v for k, v in crawler.stats.get_stats().items() if k.startswith("fusionproxy")}))
