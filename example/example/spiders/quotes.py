import json

import scrapy


class QuotesSpider(scrapy.Spider):
    """Scrapes quotes.toscrape.com through the proxy and logs the exit IP per site."""

    name = "quotes"

    async def start(self):  # Scrapy 2.13 and newer
        for request in self.start_requests():
            yield request

    def start_requests(self):  # older Scrapy
        # which IP does each site see? one sticky IP per host name
        yield scrapy.Request("https://ipinfo.io/json", callback=self.show_ip, dont_filter=True)
        yield scrapy.Request("https://ipinfo.io/json?again=1", callback=self.show_ip, dont_filter=True)
        yield scrapy.Request("https://ipinfo.io/json?de=1", callback=self.show_ip, dont_filter=True,
                             meta={"fusion_country": "de", "fusion_session": "germany"})
        yield scrapy.Request("https://quotes.toscrape.com/page/1/", callback=self.parse)

    def show_ip(self, response):
        data = json.loads(response.text)
        self.logger.info("exit IP for %s: %s (%s)", response.url, data.get("ip"), data.get("country"))

    def parse(self, response):
        for q in response.css("div.quote"):
            yield {"text": q.css("span.text::text").get(), "author": q.css("small.author::text").get()}
        next_page = response.css("li.next a::attr(href)").get()
        if next_page and response.url.rstrip("/").split("/")[-1] < "3":
            yield response.follow(next_page, self.parse)
