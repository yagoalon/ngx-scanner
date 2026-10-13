import json

import pytest
import yaml
from pathlib import Path

from pricescan.extract import extract_all, parse_price
from pricescan.products import Product, classify

CFG = yaml.safe_load((Path(__file__).parent.parent / "config.yaml").read_text())
PRODUCTS = [Product.from_dict(p) for p in CFG["products"]]


@pytest.mark.parametrize("text,expected", [
    ("2.369,00 €", 2369.0), ("€2,369.00", 2369.0), ("1 999,90 €", 1999.9),
    ("2369", 2369.0), ("2.369 €", 2369.0), ("3,999.99 $", 3999.99), ("PVP: 2.499,-", 2499.0),
    (2369, 2369.0), ("2 369,95 €", 2369.95), ("", None), ("Agotado", None),
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


def test_alerts_only_new_or_cheaper(tmp_path, monkeypatch):
    from pricescan import __main__ as m
    from pricescan.extract import Offer
    sent = []
    monkeypatch.setattr(m.notify, "send", sent.append)
    cfg = {"state_file": str(tmp_path / "s.json"), "csv_file": str(tmp_path / "h.csv")}
    p = next(x for x in PRODUCTS if x.id == "rtx5090")
    o = Offer("Gigabyte RTX 5090 Windforce 32GB", 2350, "https://s.example/1", shop="s")
    m.report([(p, o, 2350.0)], cfg, False)
    m.report([(p, o, 2350.0)], cfg, False)   # mismo precio: no repite
    m.report([(p, o, 2290.0)], cfg, False)   # baja: avisa
    m.report([(p, o, 2600.0)], cfg, False)   # sube por encima del umbral: nada
    assert len(sent) == 2 and "antes 2350" in sent[1]
