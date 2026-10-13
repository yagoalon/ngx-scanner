import json

import pytest
import yaml
from pathlib import Path

from pricescan.extract import extract_all, parse_price
from pricescan.products import Product, classify, load_products

CFG = yaml.safe_load((Path(__file__).parent.parent / "config.yaml").read_text())
PRODUCTS = load_products(CFG)


@pytest.mark.parametrize("text,expected", [
    ("2.369,00 €", 2369.0), ("€2,369.00", 2369.0), ("1 999,90 €", 1999.9),
    ("2369", 2369.0), ("2.369 €", 2369.0), ("3,999.99 $", 3999.99), ("PVP: 2.499,-", 2499.0),
    (2369, 2369.0), ("2 369,95 €", 2369.95), ("", None), ("Agotado", None),
    ("CHF 2'399.–", 2399.0), ("9 499,00 zł", 9499.0), ("£1,849.99", 1849.99),
])
def test_parse_price(text, expected):
    assert parse_price(text) == expected


@pytest.mark.parametrize("title,pid", [
    ("ASUS ROG Astral GeForce RTX 5090 OC 32GB GDDR7", "rtx5090"),
    ("NVIDIA GeForce RTX 5090 Founders Edition", "rtx5090"),
    ("Gigabyte RTX 5090 Gaming OC 32G", "rtx5090"),
    ("Portátil MSI Titan con RTX 5090 24GB", None),
    ("PC Gaming Ryzen 9 / RTX 5090", None),
    ("MSI GeForce RTX 5090 D v2 24G", None),
    ("EK-Quantum Vector waterblock RTX 5090", None),
    ("ASUS RTX 5080 16GB", None),
    ("NVIDIA DGX Spark 4TB", "gb10"),
    ("Dell Pro Max with GB10 FCM1253", "gb10"),
    ("ASUS Ascent GX10 1TB", "gb10"),
    ("Lenovo ThinkStation PGX 4TB", "gb10"),
    ("Cable QSFP para DGX Spark", None),
])
def test_classify(title, pid):
    p = classify(title, PRODUCTS)
    assert (p.id if p else None) == pid


def test_verdict():
    p = next(x for x in PRODUCTS if x.id == "rtx5090")
    assert p.verdict(2299) == "deal"
    assert p.verdict(1990) == "steal"
    assert p.verdict(3100) is None
    assert p.verdict(499) == "suspicious"


def test_jsonld():
    data = {"@context": "https://schema.org", "@graph": [{
        "@type": "Product", "name": "MSI GeForce RTX 5090 Ventus 3X OC 32GB",
        "offers": {"@type": "Offer", "price": "2349.90", "priceCurrency": "EUR",
                   "availability": "https://schema.org/InStock", "url": "/msi-5090"}}]}
    html = f'<script type="application/ld+json">{json.dumps(data)}</script>'
    [o] = extract_all(html, "https://shop.example/x")
    assert (o.price, o.url, o.in_stock) == (2349.90, "https://shop.example/msi-5090", True)


def test_heuristic_listing():
    html = """<ul>
      <li><div><a href="/p/1">Zotac GeForce RTX 5090 Solid 32GB</a></div><span class="p">2.399,00 €</span></li>
      <li><div><a href="/p/2">Funda para portátil</a></div><span class="p">19,99 €</span></li>
      <li><div><a href="/p/3">ASUS Ascent GX10 1TB GB10</a></div><b>3.299 €</b></li>
    </ul>"""
    offers = extract_all(html, "https://shop.example/s",
                         looks_relevant=lambda t: classify(t, PRODUCTS) is not None)
    got = sorted((o.url, o.price) for o in offers)
    assert got == [("https://shop.example/p/1", 2399.0), ("https://shop.example/p/3", 3299.0)]


def test_selectors():
    html = """<div class="r"><h2><a href="/dp/1">PNY RTX 5090 32GB</a></h2>
              <span class="a-price"><span class="a-offscreen">2.289,00 €</span></span></div>"""
    sel = {"item": "div.r", "title": "h2", "price": "span.a-price span.a-offscreen", "link": "a"}
    [o] = extract_all(html, "https://amazon.example/", selectors=sel)
    assert (o.price, o.url) == (2289.0, "https://amazon.example/dp/1")


def _hit(m, p, price, low=False, region=""):
    from pricescan.extract import Offer
    o = Offer("Gigabyte RTX 5090 Windforce 32GB", price, "https://s.example/1", shop="s",
              low_stock=low, region=region)
    return m.Hit(p, o, price, m.landed_cost(price, region, CFG))


def test_alerts_only_new_cheaper_or_scarce(tmp_path, monkeypatch):
    from pricescan import __main__ as m
    sent = []
    monkeypatch.setattr(m.notify, "send", sent.append)
    cfg = {"csv_file": str(tmp_path / "h.csv")}
    state = {}
    p = next(x for x in PRODUCTS if x.id == "rtx5090")
    m.report([_hit(m, p, 2350)], cfg, False, state)            # nuevo: avisa
    m.report([_hit(m, p, 2350)], cfg, False, state)            # mismo precio: no repite
    m.report([_hit(m, p, 2350, low=True)], cfg, False, state)  # pasa a últimas unidades: avisa
    m.report([_hit(m, p, 2290, low=True)], cfg, False, state)  # baja: avisa
    m.report([_hit(m, p, 2600)], cfg, False, state)            # por encima del umbral: nada
    m.report([_hit(m, p, 1950)], cfg, False, state)            # ganga
    assert len(sent) == 4
    assert "ÚLTIMAS UNIDADES" in sent[1] and "antes 2350" in sent[2] and sent[3].startswith("🚨 GANGA")


def test_notify_deals_false_keeps_only_urgent(tmp_path, monkeypatch):
    from pricescan import __main__ as m
    sent = []
    monkeypatch.setattr(m.notify, "send", sent.append)
    p = next(x for x in PRODUCTS if x.id == "rtx5090")
    m.report([_hit(m, p, 2350)], {"csv_file": None, "notify_deals": False}, False, {})
    assert sent == []


def test_landed_cost():
    from pricescan.__main__ import landed_cost
    assert landed_cost(2000, "ES", CFG) == 2000
    assert landed_cost(2000, "", CFG) == 2000
    assert landed_cost(2000, "DE", CFG) == 2020
    assert landed_cost(1720, "US", CFG) == pytest.approx(1720 * 1.21 + 80)


@pytest.mark.parametrize("text", [
    "¡Últimas unidades!", "Sólo quedan 2", "Only 1 left in stock", "Nur noch 3 Stück auf Lager",
    "Plus que 2 en stock", "Ultimi pezzi disponibili", "Nog maar 1 op voorraad", "Ostatnie sztuki",
])
def test_low_stock_phrases(text):
    from pricescan.extract import LOW_STOCK_RE
    assert LOW_STOCK_RE.search(text)


def test_low_stock_and_currency_in_listing():
    html = """<ul>
      <li><div><a href="/p/1">Zotac GeForce RTX 5090 Solid 32GB</a></div><span>£1,899.99</span><em>Only 2 left</em></li>
      <li><div><a href="/p/2">MSI GeForce RTX 5090 Ventus 32GB</a></div><span>£1,999.00</span><em>In stock</em></li>
    </ul>"""
    offers = {o.url[-1]: o for o in extract_all(html, "https://shop.example/s", region="GB",
                                                 looks_relevant=lambda t: classify(t, PRODUCTS) is not None)}
    assert offers["1"].low_stock and not offers["2"].low_stock
    assert offers["1"].currency == "GBP" and offers["1"].price == 1899.99 and offers["1"].region == "GB"


def test_jsonld_limited_availability():
    data = {"@type": "Product", "name": "NVIDIA DGX Spark 4TB",
            "offers": {"@type": "Offer", "price": 3999, "priceCurrency": "USD",
                       "availability": "https://schema.org/LimitedAvailability"}}
    html = f'<script type="application/ld+json">{json.dumps(data)}</script>'
    [o] = extract_all(html, "https://shop.example/x")
    assert o.low_stock and o.currency == "USD"


def test_config_sources_valid():
    from pricescan.sources import COUNTRIES, RUNNERS, expand_sources
    sources = expand_sources(CFG)
    names = [s["name"] for s in sources]
    assert len(names) == len(set(names)), "nombres de fuente repetidos"
    for src in sources:
        assert src["type"] in RUNNERS, src
        if src["type"] == "search":
            assert "{query}" in src["url"] and src.get("queries"), src
        if src["type"] == "page":
            assert src["urls"], src
        # YAML lee NO (Noruega), ON, Y... como booleanos: hay que ponerlos entre comillas.
        assert isinstance(src.get("region", ""), str), src["name"]
    assert all(isinstance(k, str) for k in CFG["landing"])
    by_name = {s["name"]: s for s in sources}
    for name in ("Amazon DE", "Amazon US", "eBay US", "eBay DE", "Walmart US", "Best Buy US",
                 "Alza CZ", "x-kom PL", "Komplett SE", "Galaxus FR", "Digitec CH", "MediaWorld IT"):
        assert name in by_name, name
    assert by_name["eBay US"]["currency"] == "USD" and by_name["eBay US"]["selectors"]["item"]
    assert by_name["Dell ES"]["queries"] == ["Pro Max GB10"]          # la fuente manda
    assert by_name["Amazon ES"]["queries"] == CFG["shop_queries"]      # si no, shop_queries
    assert all(c in COUNTRIES for c in by_name["Google Shopping"]["countries"])


@pytest.mark.parametrize("title", [
    "NVIDIA GeForce RTX 5090 32GB - EMPTY BOX ONLY", "RTX 5090 Founders Edition gebraucht",
    "Karta graficzna RTX 5090 używany", "RTX 5090 usato come nuovo", "Gigabyte RTX 5090 (Renewed)",
    "RTX 5090 begagnad", "ASUS RTX 5090 käytetty", "DGX Spark refurbished",
])
def test_common_exclude(title):
    assert classify(title, PRODUCTS) is None


@pytest.mark.parametrize("text", [
    "Endast 2 kvar", "Poslední kus skladem", "Kun 1 tilbage", "Vain 2 jäljellä",
    "Utolsó darabok", "Ultimele bucăți", "Only a few left", "Last one", "2 available",
])
def test_low_stock_more_languages(text):
    from pricescan.extract import LOW_STOCK_RE
    assert LOW_STOCK_RE.search(text)


def test_low_stock_no_false_positive():
    from pricescan.extract import LOW_STOCK_RE
    assert not LOW_STOCK_RE.search("More than 10 available · Free shipping")


def test_ebay_listing():
    ebay = next(s for s in CFG["sources"] if s["name"] == "eBay")
    html = """<ul>
      <li class="s-item"><a class="s-item__link" href="https://ebay.example/itm/0">
        <div class="s-item__title">Shop on eBay</div></a><span class="s-item__price">$20.00</span></li>
      <li class="s-item"><a class="s-item__link" href="https://ebay.example/itm/1">
        <div class="s-item__title">New Listing MSI GeForce RTX 5090 32GB Gaming Trio OC</div></a>
        <span class="s-item__price">EUR 2.149,00</span><span>Last one</span></li>
    </ul>"""
    offers = extract_all(html, "https://www.ebay.com/sch", selectors=ebay["selectors"], currency="USD")
    o = next(x for x in offers if classify(x.title, PRODUCTS))
    assert (o.price, o.currency, o.low_stock, o.url) == (2149.0, "EUR", True, "https://ebay.example/itm/1")


def test_load_dotenv(tmp_path, monkeypatch):
    from pricescan.__main__ import load_dotenv
    import os
    (tmp_path / ".env").write_text('# comentario\nPRICESCAN_A="x y"\nPRICESCAN_B=\nPRICESCAN_C=ya\n')
    monkeypatch.delenv("PRICESCAN_A", raising=False)
    monkeypatch.setenv("PRICESCAN_C", "antes")
    load_dotenv(tmp_path / ".env")
    assert os.environ["PRICESCAN_A"] == "x y" and os.environ["PRICESCAN_B"] == ""
    assert os.environ["PRICESCAN_C"] == "antes"   # no pisa lo ya definido
    load_dotenv(tmp_path / "no-existe")
