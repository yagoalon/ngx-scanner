"""Extracción de ofertas (título, precio, enlace) desde HTML.

Estrategias, en orden:
  1. JSON-LD (schema.org Product / Offer / ItemList) — lo usan casi todas las tiendas.
  2. Microdatos (itemprop="price").
  3. Selectores CSS definidos en la configuración de la fuente.
  4. Heurística genérica: enlaces cuyo texto parece un producto + el precio más cercano.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Iterable, Iterator
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag


@dataclass
class Offer:
    title: str
    price: float
    url: str
    currency: str = "EUR"
    shop: str = ""
    in_stock: bool | None = None

    def key(self) -> str:
        return self.url.split("#")[0]


_PRICE_RE = re.compile(
    r"(?:€|eur|usd|\$|£)?\s*(\d{1,3}(?:[.,\s  ]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s*(?:€|eur|usd|\$|£)?",
    re.IGNORECASE,
)
_CURRENCY_HINT = re.compile(r"€|eur\b|\$|usd\b|£", re.IGNORECASE)


def parse_price(value) -> float | None:
    """Convierte '2.369,00 €', '€2,369.00', '1 999,90', 2369 ... en float."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    text = str(value).strip()
    m = _PRICE_RE.search(text)
    if not m:
        return None
    raw = re.sub(r"[\s  ]", "", m.group(1))
    if "," in raw and "." in raw:
        # El último separador es el decimal.
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw or "." in raw:
        sep = "," if "," in raw else "."
        head, _, tail = raw.rpartition(sep)
        if len(tail) == 3:
            raw = raw.replace(sep, "")  # separador de miles: 2.369 / 2,369
        else:
            raw = head.replace(sep, "") + "." + tail
    try:
        price = float(raw)
    except ValueError:
        return None
    return price if price > 0 else None


def _availability(value) -> bool | None:
    if not value:
        return None
    v = str(value).lower()
    if any(s in v for s in ("instock", "in_stock", "limitedavailability", "preorder", "presale")):
        return True
    if any(s in v for s in ("outofstock", "out_of_stock", "soldout", "discontinued")):
        return False
    return None


# ---------------------------------------------------------------- JSON-LD

def _walk_jsonld(node) -> Iterator[dict]:
    if isinstance(node, list):
        for n in node:
            yield from _walk_jsonld(n)
    elif isinstance(node, dict):
        yield node
        for key in ("@graph", "itemListElement", "item", "mainEntity", "isRelatedTo", "hasVariant"):
            if key in node:
                yield from _walk_jsonld(node[key])


def _types(node: dict) -> set[str]:
    t = node.get("@type", [])
    return {x.lower() for x in (t if isinstance(t, list) else [t]) if isinstance(x, str)}


def _offers_from_product(node: dict, base_url: str, shop: str) -> Iterator[Offer]:
    title = (node.get("name") or "").strip()
    url = urljoin(base_url, node.get("url") or base_url)
    offers = node.get("offers") or []
    for off in offers if isinstance(offers, list) else [offers]:
        if not isinstance(off, dict):
            continue
        price = parse_price(off.get("price") or off.get("lowPrice"))
        if price is None and isinstance(off.get("priceSpecification"), dict):
            price = parse_price(off["priceSpecification"].get("price"))
        if price is None or not title:
            continue
        yield Offer(
            title=title,
            price=price,
            url=urljoin(base_url, off.get("url") or url),
            currency=(off.get("priceCurrency") or "EUR").upper(),
            shop=shop,
            in_stock=_availability(off.get("availability")),
        )


def from_jsonld(soup: BeautifulSoup, base_url: str, shop: str = "") -> list[Offer]:
    found: list[Offer] = []
    for script in soup.find_all("script", type=re.compile("ld\\+json", re.I)):
        try:
            data = json.loads(script.string or script.get_text() or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for node in _walk_jsonld(data):
            if "product" in _types(node) or ("offers" in node and "name" in node):
                found.extend(_offers_from_product(node, base_url, shop))
    return found


# ------------------------------------------------------------- Microdatos

def from_microdata(soup: BeautifulSoup, base_url: str, shop: str = "") -> list[Offer]:
    found: list[Offer] = []
    for prod in soup.select('[itemtype*="schema.org/Product"]'):
        name = prod.select_one('[itemprop="name"]')
        price = prod.select_one('[itemprop="price"]')
        if not (name and price):
            continue
        value = parse_price(price.get("content") or price.get_text())
        link = prod.select_one('[itemprop="url"]') or prod.find("a", href=True)
        href = (link.get("href") or link.get("content")) if link else base_url
        cur = prod.select_one('[itemprop="priceCurrency"]')
        avail = prod.select_one('[itemprop="availability"]')
        if value:
            found.append(Offer(
                title=(name.get("content") or name.get_text()).strip(),
                price=value,
                url=urljoin(base_url, href),
                currency=(cur.get("content") if cur else "EUR") or "EUR",
                shop=shop,
                in_stock=_availability((avail.get("href") or avail.get("content")) if avail else None),
            ))
    return found


# --------------------------------------------------------- Selectores CSS

def from_selectors(soup: BeautifulSoup, base_url: str, sel: dict, shop: str = "") -> list[Offer]:
    """sel = {item: '...', title: '...', price: '...', link: '...'} (link opcional)."""
    found: list[Offer] = []
    for item in soup.select(sel["item"]):
        t = item.select_one(sel["title"]) if sel.get("title") else item
        p = item.select_one(sel["price"])
        if not (t and p):
            continue
        a = item.select_one(sel["link"]) if sel.get("link") else (t if t.name == "a" else t.find("a", href=True) or item.find("a", href=True))
        price = parse_price(p.get("content") or p.get_text(" "))
        if price is None:
            continue
        found.append(Offer(
            title=(t.get("title") or t.get_text(" ")).strip(),
            price=price,
            url=urljoin(base_url, a.get("href")) if a is not None and a.get("href") else base_url,
            shop=shop,
        ))
    return found


# ---------------------------------------------------- Heurística genérica

def _container_price(a: Tag, max_depth: int = 6) -> float | None:
    node: Tag | None = a
    for _ in range(max_depth):
        node = node.parent if node is not None else None
        if node is None or node.name in ("body", "html"):
            return None
        # Sólo consideramos textos con símbolo de moneda para evitar números sueltos.
        for text in node.find_all(string=_CURRENCY_HINT):
            chunk = text.strip()
            if len(chunk) > 40:  # no es una etiqueta de precio
                continue
            price = parse_price(chunk)
            if price is None:
                # p.ej. "2.369" en un <span> y "€" en otro
                sib = text.parent.get_text(" ", strip=True) if text.parent else ""
                price = parse_price(sib) if len(sib) <= 40 else None
            if price:
                return price
        if len(node.find_all("a", href=True)) > 8:
            return None  # hemos subido demasiado: contenedor de varios productos
    return None


def heuristic(soup: BeautifulSoup, base_url: str, looks_relevant, shop: str = "") -> list[Offer]:
    found: dict[str, Offer] = {}
    for a in soup.find_all("a", href=True):
        title = (a.get("title") or a.get_text(" ", strip=True) or "").strip()
        if len(title) < 8 or not looks_relevant(title):
            continue
        url = urljoin(base_url, a["href"])
        if url in found:
            continue
        price = _container_price(a)
        if price:
            found[url] = Offer(title=title, price=price, url=url, shop=shop)
    return list(found.values())


def extract_all(html: str, base_url: str, *, shop: str = "", selectors: dict | None = None,
                looks_relevant=lambda t: True) -> list[Offer]:
    soup = BeautifulSoup(html, "lxml")
    offers: list[Offer] = []
    if selectors:
        offers += from_selectors(soup, base_url, selectors, shop)
    offers += from_jsonld(soup, base_url, shop)
    offers += from_microdata(soup, base_url, shop)
    if not offers:
        offers += heuristic(soup, base_url, looks_relevant, shop)
    return dedupe(offers)


def dedupe(offers: Iterable[Offer]) -> list[Offer]:
    best: dict[str, Offer] = {}
    for o in offers:
        k = o.key()
        if k not in best or o.price < best[k].price:
            best[k] = o
    return list(best.values())
