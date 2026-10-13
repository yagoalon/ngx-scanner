"""Fuentes de ofertas: páginas de producto, buscadores de tiendas y Google Shopping (SerpAPI)."""
from __future__ import annotations

import logging
import os
import random
import time
from urllib.parse import quote_plus, urlparse

import requests

from .extract import Offer, extract_all, parse_price
from .products import Product

log = logging.getLogger("pricescan")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8,de;q=0.7,fr;q=0.6,it;q=0.5",
}

# País → (idioma, dominio de Google, moneda) para Google Shopping.
COUNTRIES = {
    "es": ("es", "google.es", "EUR"), "pt": ("pt", "google.pt", "EUR"), "fr": ("fr", "google.fr", "EUR"),
    "de": ("de", "google.de", "EUR"), "at": ("de", "google.at", "EUR"), "it": ("it", "google.it", "EUR"),
    "nl": ("nl", "google.nl", "EUR"), "be": ("nl", "google.be", "EUR"), "ie": ("en", "google.ie", "EUR"),
    "fi": ("fi", "google.fi", "EUR"), "gr": ("el", "google.gr", "EUR"), "sk": ("sk", "google.sk", "EUR"),
    "pl": ("pl", "google.pl", "PLN"), "cz": ("cs", "google.cz", "CZK"), "se": ("sv", "google.se", "SEK"),
    "dk": ("da", "google.dk", "DKK"), "no": ("no", "google.no", "NOK"), "hu": ("hu", "google.hu", "HUF"),
    "ro": ("ro", "google.ro", "RON"), "ch": ("de", "google.ch", "CHF"), "gb": ("en", "google.co.uk", "GBP"),
    "us": ("en", "google.com", "USD"),
}


class Fetcher:
    def __init__(self, delay: tuple[float, float] = (2.0, 5.0), timeout: int = 25):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.delay = delay
        self.timeout = timeout
        self._browser = None
        self._pw = None

    def get(self, url: str, render: bool = False) -> str | None:
        time.sleep(random.uniform(*self.delay))  # sé amable con las tiendas
        try:
            if render:
                return self._render(url)
            r = self.session.get(url, timeout=self.timeout)
            if r.status_code in (403, 429, 503):
                log.warning("%s → HTTP %s (anti-bot). Prueba 'render: true' en esa fuente.", url, r.status_code)
                return None
            r.raise_for_status()
            return r.text
        except Exception as e:  # noqa: BLE001 — una fuente rota no debe parar el resto
            log.warning("Error descargando %s: %s", url, e)
            return None

    def _render(self, url: str) -> str | None:
        """Renderiza con Chromium (Playwright) para webs con JavaScript / anti-bot ligero."""
        if self._browser is None:
            from playwright.sync_api import sync_playwright  # import perezoso: dependencia opcional
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(headless=True)
        page = self._browser.new_page(user_agent=HEADERS["User-Agent"], locale="es-ES")
        try:
            page.goto(url, timeout=self.timeout * 1000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            return page.content()
        finally:
            page.close()

    def close(self):
        if self._browser:
            self._browser.close()
            self._pw.stop()


def _shop_name(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _queries(src: dict, products: list[Product]) -> list[tuple[str, Product | None]]:
    """Búsquedas a lanzar: las de la fuente (si las define) o las de cada producto."""
    if src.get("queries"):
        return [(q, None) for q in src["queries"]]
    return [(q, p) for p in products for q in p.queries]


def _relevant(products: list[Product], only: Product | None):
    return only.matches if only else (lambda t: any(p.matches(t) for p in products))


def run_page(src: dict, fetcher: Fetcher, products: list[Product]) -> list[Offer]:
    """Páginas de producto concretas (ficha de la tienda, NVIDIA Marketplace, Dell...)."""
    offers: list[Offer] = []
    for url in src.get("urls", []):
        html = fetcher.get(url, render=src.get("render", False))
        if html:
            offers += extract_all(html, url, shop=src.get("name") or _shop_name(url),
                                  selectors=src.get("selectors"), looks_relevant=_relevant(products, None),
                                  currency=src.get("currency", "EUR"), region=src.get("region", ""))
    return offers


def run_search(src: dict, fetcher: Fetcher, products: list[Product]) -> list[Offer]:
    """Buscador interno de una tienda o comparador: url con {query}."""
    offers: list[Offer] = []
    for q, product in _queries(src, products):
        url = src["url"].replace("{query}", quote_plus(q))
        html = fetcher.get(url, render=src.get("render", False))
        if html:
            offers += extract_all(html, url, shop=src.get("name") or _shop_name(url),
                                  selectors=src.get("selectors"), looks_relevant=_relevant(products, product),
                                  currency=src.get("currency", "EUR"), region=src.get("region", ""))
    return offers


def run_serpapi(src: dict, fetcher: Fetcher, products: list[Product]) -> list[Offer]:
    """Google Shopping vía SerpAPI en varios países: cientos de tiendas de Europa y EE. UU."""
    key = os.environ.get(src.get("api_key_env", "SERPAPI_KEY"))
    if not key:
        log.info("SerpAPI desactivado (falta la variable %s).", src.get("api_key_env", "SERPAPI_KEY"))
        return []
    offers: list[Offer] = []
    for country in src.get("countries", ["es"]):
        hl, domain, currency = COUNTRIES[country.lower()]
        for q, _ in _queries(src, products):
            params = {"engine": "google_shopping", "q": q, "api_key": key,
                      "gl": country.lower(), "hl": hl, "google_domain": domain, "num": 60}
            try:
                r = requests.get("https://serpapi.com/search.json", params=params, timeout=40)
                r.raise_for_status()
                data = r.json()
            except Exception as e:  # noqa: BLE001
                log.warning("SerpAPI %s '%s': %s", country, q, e)
                continue
            for item in data.get("shopping_results", []) + data.get("inline_shopping_results", []):
                if item.get("second_hand_condition"):
                    continue  # sólo nuevo
                price = item.get("extracted_price") or parse_price(item.get("price"))
                link = item.get("link") or item.get("product_link")
                if price and link and item.get("title"):
                    offers.append(Offer(title=item["title"], price=float(price), url=link, currency=currency,
                                        shop=f"{item.get('source', 'google')} ({country.upper()})",
                                        region=country.upper()))
    return offers


RUNNERS = {"page": run_page, "search": run_search, "serpapi": run_serpapi}
