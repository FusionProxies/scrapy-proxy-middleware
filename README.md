<p align="center">
  <a href="https://fusionproxy.net/?utm_source=github&utm_medium=scrapy-proxy-middleware">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/FusionProxies/.github/main/assets/logo-on-dark.png">
      <img src="https://raw.githubusercontent.com/FusionProxies/.github/main/assets/logo-on-light.png" alt="Fusion Proxy" height="52">
    </picture>
  </a>
</p>

# Scrapy proxy middleware for rotating residential proxies

A Scrapy downloader middleware that sends your crawl through rotating residential proxies and handles the parts that usually need custom code:

- **Country targeting** for the whole project or per request
- **Sticky sessions per website**: every site keeps one residential IP for the time you set, so cookies and sessions stay consistent
- **New IP on a block**: on `403`, `429`, a captcha page or a dropped connection, the site moves to a fresh IP and the request is retried
- **Stats** in the Scrapy log: requests, rotations, blocks per status code

Made for [Fusion Proxy](https://fusionproxy.net/proxies/residential?utm_source=github&utm_medium=scrapy-proxy-middleware) residential proxies; the gateway host and port are settings, so it works with any gateway that takes options in the username.

## Install

```bash
pip install git+https://github.com/FusionProxies/scrapy-proxy-middleware
```

## Configure

`settings.py`:

```python
DOWNLOADER_MIDDLEWARES = {
    "scrapy_fusionproxy.FusionProxyMiddleware": 610,
}

FUSIONPROXY_USER = "your_username"      # or set FUSION_USER in the environment
FUSIONPROXY_PASS = "your_password"      # or FUSION_PASS
FUSIONPROXY_COUNTRY = "us"              # optional, two-letter country code
FUSIONPROXY_STICKY_MINUTES = 10         # 0 = a new IP on every connection
```

Priority `610` puts it before Scrapy's own `HttpProxyMiddleware` (750), which turns the credentials into the `Proxy-Authorization` header, and before `RetryMiddleware` (550) in the response chain, so a block is answered with a new IP before Scrapy's plain retry sees it.

## All settings

| Setting | Default | Meaning |
|---|---|---|
| `FUSIONPROXY_USER`, `FUSIONPROXY_PASS` | env `FUSION_USER`, `FUSION_PASS` | Proxy credentials |
| `FUSIONPROXY_COUNTRY` | none | Exit country for every request |
| `FUSIONPROXY_STICKY_MINUTES` | `10` | How long a website keeps its IP (1 to 120). `0` rotates on every connection |
| `FUSIONPROXY_BAN_CODES` | `[403, 429]` | Status codes treated as a block |
| `FUSIONPROXY_BAN_TEXT` | `["captcha", "access denied"]` | Text in a short `200` page that means a block page |
| `FUSIONPROXY_MAX_ROTATIONS` | `3` | New IPs to try for one request before giving up |
| `FUSIONPROXY_HOST`, `FUSIONPROXY_PORT` | `resi.fusionproxy.net`, `12286` | Gateway |

## Per-request options

```python
yield scrapy.Request(url, meta={"fusion_country": "de"})        # this request from Germany
yield scrapy.Request(url, meta={"fusion_session": "account-7"}) # own sticky IP for this key
yield scrapy.Request(url, meta={"fusion_proxy": False})         # skip the proxy
```

By default the sticky key is the website's host name, so `example.com` and `example.org` get different IPs and each keeps its own.

## Example project

[`example/`](example) scrapes [quotes.toscrape.com](https://quotes.toscrape.com) and logs the IP each site sees:

```bash
cd example
export FUSION_USER="your_username" FUSION_PASS="your_password"
scrapy crawl quotes -O quotes.json
```

```
[quotes] INFO: exit IP for https://ipinfo.io/json: 47.222.79.127 (US)
[quotes] INFO: exit IP for https://ipinfo.io/json?again=1: 47.222.79.127 (US)
[quotes] INFO: exit IP for https://ipinfo.io/json?de=1: 91.52.84.36 (DE)
 'fusionproxy/requests': 8,
 'item_scraped_count': 30,
```

The same site keeps its IP, and the request with `fusion_country: "de"` gets a German one. When a site blocks, the log shows the rotation:

```
[ban] INFO: fusionproxy: HTTP 429 on https://httpbin.org/status/429, retrying from a new IP
[ban] INFO: fusionproxy: HTTP 429 on https://httpbin.org/status/429, retrying from a new IP
[ban] INFO: fusionproxy: HTTP 429 on https://httpbin.org/status/429, retrying from a new IP
[ban] WARNING: fusionproxy: giving up on https://httpbin.org/status/429 after 3 new IPs (HTTP 429)
```

## Tips

- Keep `DOWNLOAD_DELAY` and `AUTOTHROTTLE_ENABLED` on. A new IP does not make hammering a site acceptable, and slower crawls get blocked less.
- `CONCURRENT_REQUESTS_PER_DOMAIN` above 8 on one sticky IP looks like a bot. Lower it, or use `fusion_session` keys to spread a site over several IPs.
- Scrapy reuses proxy tunnels. Requests on one tunnel share its IP, which is what sticky sessions want; with `FUSIONPROXY_STICKY_MINUTES = 0` a new IP comes with each new connection.

## Related

- [python-requests-proxy](https://github.com/FusionProxies/python-requests-proxy): proxies in Python requests
- [python-web-scraping](https://github.com/FusionProxies/python-web-scraping): a requests + BeautifulSoup scraper
- [proxy-checker](https://github.com/FusionProxies/proxy-checker): check proxies from the command line

Need proxies? [Fusion Proxy residential proxies](https://fusionproxy.net/proxies/residential?utm_source=github&utm_medium=scrapy-proxy-middleware) start at $2.95/GB, with a [free trial](https://fusionproxy.net/free-trial?utm_source=github&utm_medium=scrapy-proxy-middleware).

## License

MIT, see [LICENSE](LICENSE).
