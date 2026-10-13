"""Extracción de ofertas (título, precio, moneda, stock, enlace) desde HTML.

Estrategias, en orden:
  1. Selectores CSS definidos en la configuración de la fuente.
  2. JSON-LD (schema.org Product / Offer / ItemList) — lo usan casi todas las tiendas.
  3. Microdatos (itemprop="price").
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
    low_stock: bool = False      # "últimas unidades", "only 2 left", LimitedAvailability...
    region: str = ""             # país de la tienda (ES, DE, US...) para estimar coste puesto en casa

    def key(self) -> str:
        return self.url.split("#")[0]


_SEP = r"[.,\s  '’]"
_PRICE_RE = re.compile(rf"(\d{{1,3}}(?:{_SEP}\d{{3}})+(?:[.,]\d{{1,2}})?|\d+(?:[.,]\d{{1,2}})?)")
_CURRENCIES = [  # (regex, código ISO)
    (r"€|\beur\b", "EUR"), (r"£|\bgbp\b", "GBP"), (r"\bchf\b", "CHF"), (r"zł|\bpln\b", "PLN"),
    (r"kč|\bczk\b", "CZK"), (r"\bsek\b", "SEK"), (r"\bdkk\b", "DKK"), (r"\bnok\b", "NOK"),
    (r"\bhuf\b|\bft\b", "HUF"), (r"\bron\b|\blei\b", "RON"), (r"us\$|\busd\b|\$", "USD"),
]
_CURRENCY_HINT = re.compile("|".join(r for r, _ in _CURRENCIES), re.IGNORECASE)

# Frases de "quedan pocas" en los idiomas de las tiendas vigiladas.
LOW_STOCK_RE = re.compile(
    r"[úu]ltimas? unidad|s[oó]lo quedan?|quedan? (?:s[oó]lo )?\d+ |pocas unidades|"
    r"only \d+ left|last (?:one|few|units?)|low (?:in )?stock|few left|limited stock|"
    r"nur noch \d+|letzte(?:n)? (?:st[üu]ck|exemplar)|wenige auf lager|geringer bestand|"
    r"plus que \d+|derni[eè]res? (?:pi[eè]ces?|unit[eé]s?|exemplaires?)|stock limit[eé]|"
    r"ultimi (?:pezzi|disponibili)|solo \d+ disponibil|disponibilit[aà] limitata|"
    r"apenas \d+ (?:em|dispon)|"
    r"nog (?:maar )?\d+ (?:op voorraad|beschikbaar)|laatste (?:stuks|exemplaren)|"
    r"ostatnie sztuki|tylko \d+ szt|"
    r"posledn[ií] kus|posledn[eé] kusy|zbyv[aá] (?:posledn|jen)|"            # CZ / SK
    r"f[åa] kvar|endast \d+ kvar|bara \d+ kvar|sista exemplar|"              # SE
    r"kun \d+ (?:tilbage|igjen|p[åa] lager)|f[åa] (?:tilbage|igjen|p[åa] lager)|"  # DK / NO
    r"vain \d+ j[äa]ljell[äa]|viimeiset kappaleet|v[äa]h[äa]n j[äa]ljell[äa]|"    # FI
    r"utols[oó] darab|csak \d+ db|"                                         # HU
    r"ultimele (?:buc|produse)|stoc limitat|"                               # RO
    r"τελευτα[ίι]α τεμ[άα]χια|"                                              # GR
    r"only a few left|almost gone|last one|\b[1-3] (?:available|disponibles?|verf[üu]gbar|disponibili)\b",  # eBay / Walmart / Best Buy
    re.IGNORECASE,
)


def detect_currency(text: str) -> str | None:
    for rx, code in _CURRENCIES:
        if re.search(rx, text, re.IGNORECASE):
            return code
    return None


def parse_price(value) -> float | None:
    """Convierte '2.369,00 €', '€2,369.00', '1 999,90', "CHF 2'399.–", 2369 ... en float."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    m = _PRICE_RE.search(str(value))
    if not m:
        return None
    raw = re.sub(r"[\s  '’]", "", m.group(1))
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


def _availability(value) -> tuple[bool | None, bool]:
    """→ (en_stock, pocas_unidades)."""
    if not value:
        return None, False
    v = str(value).lower()
    if "limitedavailability" in v:
        return True, True
    if any(s in v for s in ("instock", "in_stock", "preorder", "presale", "onlineonly")):
        return True, False
    if any(s in v for s in ("outofstock", "out_of_stock", "soldout", "discontinued")):
        return False, False
    return None, False


def _inventory_low(off: dict, threshold: int = 3) -> bool:
    inv = off.get("inventoryLevel")
    if isinstance(inv, dict):
        inv = inv.get("value")
    try:
        return 0 < int(float(inv)) <= threshold
    except (TypeError, ValueError):
        return False


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


def _offers_from_product(node: dict, base_url: str, shop: str, currency: str) -> Iterator[Offer]:
    title = (node.get("name") or "").strip()
    url = urljoin(base_url, node.get("url") or base_url)
    offers = node.get("offers") or []
    for off in offers if isinstance(offers, list) else [offers]:
        if not isinstance(off, dict):
            continue
        # AggregateOffer → su lista interna de ofertas
        if "offers" in off and isinstance(off["offers"], list):
            yield from _offers_from_product({**node, "offers": off["offers"]}, base_url, shop, currency)
            continue
        price = parse_price(off.get("price") or off.get("lowPrice"))
        if price is None and isinstance(off.get("priceSpecification"), dict):
            price = parse_price(off["priceSpecification"].get("price"))
        if price is None or not title:
            continue
        in_stock, low = _availability(off.get("availability"))
        yield Offer(
            title=title, price=price, url=urljoin(base_url, off.get("url") or url),
            currency=(off.get("priceCurrency") or currency).upper(), shop=shop,
            in_stock=in_stock, low_stock=low or _inventory_low(off),
        )


def from_jsonld(soup: BeautifulSoup, base_url: str, shop: str = "", currency: str = "EUR") -> list[Offer]:
    found: list[Offer] = []
    for script in soup.find_all("script", type=re.compile("ld\\+json", re.I)):
        try:
            data = json.loads(script.string or script.get_text() or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for node in _walk_jsonld(data):
            if "product" in _types(node) or ("offers" in node and "name" in node):
                found.extend(_offers_from_product(node, base_url, shop, currency))
    return found


# ------------------------------------------------------------- Microdatos

def from_microdata(soup: BeautifulSoup, base_url: str, shop: str = "", currency: str = "EUR") -> list[Offer]:
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
        in_stock, low = _availability((avail.get("href") or avail.get("content")) if avail else None)
        if value:
            found.append(Offer(
                title=(name.get("content") or name.get_text()).strip(), price=value,
                url=urljoin(base_url, href), currency=(cur.get("content") if cur else None) or currency,
                shop=shop, in_stock=in_stock,
                low_stock=low or bool(LOW_STOCK_RE.search(prod.get_text(" "))),
            ))
    return found


# --------------------------------------------------------- Selectores CSS

def from_selectors(soup: BeautifulSoup, base_url: str, sel: dict, shop: str = "", currency: str = "EUR") -> list[Offer]:
    """sel = {item, title, price, link?, stock?} — 'stock' apunta al texto de disponibilidad."""
    found: list[Offer] = []
    for item in soup.select(sel["item"]):
        t = item.select_one(sel["title"]) if sel.get("title") else item
        p = item.select_one(sel["price"])
        if not (t and p):
            continue
        a = item.select_one(sel["link"]) if sel.get("link") else (t if t.name == "a" else t.find("a", href=True) or item.find("a", href=True))
        ptext = p.get("content") or p.get_text(" ")
        price = parse_price(ptext)
        if price is None:
            continue
        stock_node = item.select_one(sel["stock"]) if sel.get("stock") else item
        found.append(Offer(
            title=(t.get("title") or t.get_text(" ")).strip(), price=price,
            url=urljoin(base_url, a.get("href")) if a is not None and a.get("href") else base_url,
            currency=detect_currency(ptext) or currency, shop=shop,
            low_stock=bool(stock_node and LOW_STOCK_RE.search(stock_node.get_text(" "))),
        ))
    return found


# ---------------------------------------------------- Heurística genérica

def _container(a: Tag, max_depth: int = 6) -> tuple[Tag, float, str] | None:
    """Sube desde el enlace hasta el bloque que contiene su precio → (bloque, precio, moneda)."""
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
                return node, price, detect_currency(chunk) or ""
        if len(node.find_all("a", href=True)) > 8:
            return None  # hemos subido demasiado: contenedor de varios productos
    return None


def heuristic(soup: BeautifulSoup, base_url: str, looks_relevant, shop: str = "", currency: str = "EUR") -> list[Offer]:
    found: dict[str, Offer] = {}
    for a in soup.find_all("a", href=True):
        title = (a.get("title") or a.get_text(" ", strip=True) or "").strip()
        if len(title) < 8 or not looks_relevant(title):
            continue
        url = urljoin(base_url, a["href"])
        if url in found:
            continue
        hit = _container(a)
        if hit:
            box, price, cur = hit
            found[url] = Offer(title=title, price=price, url=url, currency=cur or currency, shop=shop,
                               low_stock=bool(LOW_STOCK_RE.search(box.get_text(" "))))
    return list(found.values())


def extract_all(html: str, base_url: str, *, shop: str = "", selectors: dict | None = None,
                looks_relevant=lambda t: True, currency: str = "EUR", region: str = "") -> list[Offer]:
    soup = BeautifulSoup(html, "lxml")
    offers: list[Offer] = []
    if selectors:
        offers += from_selectors(soup, base_url, selectors, shop, currency)
    offers += from_jsonld(soup, base_url, shop, currency)
    offers += from_microdata(soup, base_url, shop, currency)
    if not offers:
        offers += heuristic(soup, base_url, looks_relevant, shop, currency)
    # Ficha de un único producto: el aviso de "últimas unidades" puede estar en cualquier parte de la página.
    relevant = [o for o in offers if looks_relevant(o.title)]
    if len(relevant) == 1 and LOW_STOCK_RE.search(soup.get_text(" ")):
        relevant[0].low_stock = True
    for o in offers:
        o.region = o.region or region
    return dedupe(offers)


def dedupe(offers: Iterable[Offer]) -> list[Offer]:
    best: dict[str, Offer] = {}
    for o in offers:
        k = o.key()
        if k not in best or o.price < best[k].price:
            best[k] = o
    return list(best.values())
