"""Uso:
    python -m pricescan                      # una pasada con config.yaml
    python -m pricescan --loop 30            # repetir cada ~30 min
    python -m pricescan --all                # listar todo lo encontrado, no sólo chollos
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

from . import notify
from .extract import Offer, dedupe
from .fx import eur_rates
from .products import Product, classify
from .sources import RUNNERS, Fetcher

log = logging.getLogger("pricescan")


@dataclass
class Hit:
    product: Product
    offer: Offer
    eur: float       # precio de la tienda convertido a EUR
    landed: float    # coste estimado puesto en casa (IVA de importación + envío)


def load_config(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def landed_cost(eur: float, region: str, cfg: dict) -> float:
    """Coste estimado en casa. Las tiendas de tu país no llevan recargo."""
    region = (region or "").upper()
    if not region or region == cfg.get("home_region", "ES").upper():
        return eur
    rules = cfg.get("landing", {})
    rule = rules.get(region) or rules.get("default") or {}
    return eur * float(rule.get("factor", 1.0)) + float(rule.get("extra_eur", 0))


def _due(src: dict, state: dict) -> bool:
    """Respeta 'every_minutes' (útil para fuentes de pago como SerpAPI)."""
    every = src.get("every_minutes")
    if not every:
        return True
    last = state.get("__sources__", {}).get(src.get("name", src["type"]), 0)
    return time.time() - last >= every * 60 * 0.95


def scan(cfg: dict, state: dict) -> list[Hit]:
    products = [Product.from_dict(p) for p in cfg["products"]]
    fetcher = Fetcher(delay=tuple(cfg.get("delay_seconds", [2, 5])))
    raw: list[Offer] = []
    try:
        for src in cfg.get("sources", []):
            name = src.get("name", src["type"])
            if src.get("enabled", True) is False:
                continue
            if not _due(src, state):
                log.info("%-28s (saltada: toca cada %s min)", name, src["every_minutes"])
                continue
            got = RUNNERS[src["type"]](src, fetcher, products)
            state.setdefault("__sources__", {})[name] = time.time()
            log.info("%-28s %3d ofertas", name, len(got))
            raw += got
    finally:
        fetcher.close()

    rates = eur_rates(cfg.get("fx_to_eur", {}))
    hits = []
    for offer in dedupe(raw):
        if offer.in_stock is False and not cfg.get("include_out_of_stock", False):
            continue
        product = classify(offer.title, products)
        rate = rates.get((offer.currency or "EUR").upper())
        if product and rate:
            eur = round(offer.price * rate, 2)
            hits.append(Hit(product, offer, eur, round(landed_cost(eur, offer.region, cfg), 2)))
    hits.sort(key=lambda h: (h.product.id, h.landed))
    return hits


def load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _price_text(h: Hit) -> str:
    o = h.offer
    local = "" if o.currency == "EUR" else f"{o.price:,.0f} {o.currency} → "
    extra = f" (≈{h.landed:.0f} € puesto en casa)" if h.landed != h.eur else ""
    return f"{local}{h.eur:.2f} €{extra}"


def report(hits: list[Hit], cfg: dict, show_all: bool, state: dict) -> None:
    notify_deals = cfg.get("notify_deals", True)
    alerts = []
    for h in hits:
        o, p = h.offer, h.product
        verdict = p.verdict(h.landed)
        prev = state.get(o.key(), {})
        state[o.key()] = {"price": h.landed, "low_stock": o.low_stock, "title": o.title,
                          "seen": datetime.now().isoformat(timespec="minutes")}
        tags = {"steal": "🚨 GANGA", "deal": "🔥 CHOLLO", "suspicious": "⚠️ SOSPECHOSO"}.get(verdict, "")
        if o.low_stock:
            tags += " ⏳ÚLTIMAS"
        if show_all or verdict:
            print(f"{tags:22} [{p.id}] {_price_text(h)}  {o.shop}\n{'':23}{o.title[:90]}\n{'':23}{o.url}")

        if verdict not in ("steal", "deal"):
            continue
        cheaper = "price" not in prev or h.landed < prev["price"] - 0.5
        became_scarce = o.low_stock and not prev.get("low_stock")
        important = verdict == "steal" or o.low_stock or notify_deals
        if important and (cheaper or became_scarce):
            head = "🚨 GANGA" if verdict == "steal" else "🔥 Buen precio"
            if o.low_stock:
                head += " · ⏳ ÚLTIMAS UNIDADES"
            delta = f" (antes {prev['price']:.0f} €)" if prev.get("price") and cheaper else ""
            alerts.append(f"{head}\n{p.name}: {_price_text(h)}{delta}\n"
                          f"Umbral {p.max_price:.0f} € · ganga ≤ {p.steal_price:.0f} €\n"
                          f"{o.title}\n{o.shop}\n{o.url}")

    if out := cfg.get("csv_file"):
        new = not Path(out).exists()
        with open(out, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["fecha", "producto", "precio_local", "moneda", "precio_eur", "coste_en_casa_eur",
                            "ultimas_unidades", "region", "tienda", "titulo", "url"])
            now = datetime.now().isoformat(timespec="minutes")
            for h in hits:
                o = h.offer
                w.writerow([now, h.product.id, o.price, o.currency, h.eur, h.landed,
                            int(o.low_stock), o.region, o.shop, o.title, o.url])

    log.info("%d ofertas relevantes, %d avisos nuevos.", len(hits), len(alerts))
    # Lo más urgente primero.
    for text in sorted(alerts, key=lambda t: (not t.startswith("🚨"), "ÚLTIMAS" not in t)):
        notify.send(text)


def main() -> None:
    ap = argparse.ArgumentParser(prog="pricescan", description="Vigila precios de DGX Spark / GB10 y RTX 5090.")
    ap.add_argument("-c", "--config", default="config.yaml", type=Path)
    ap.add_argument("--loop", type=float, metavar="MIN", help="repetir cada MIN minutos")
    ap.add_argument("--all", action="store_true", help="mostrar todas las ofertas, no sólo chollos")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    while True:
        cfg = load_config(args.config)  # recarga en cada vuelta: puedes editar umbrales en caliente
        state_path = Path(cfg.get("state_file", "state.json"))
        state = load_state(state_path)
        report(scan(cfg, state), cfg, args.all, state)
        state_path.write_text(json.dumps(state, indent=1, ensure_ascii=False))
        if not args.loop:
            break
        wait = args.loop * 60 * random.uniform(0.85, 1.15)
        log.info("Siguiente pasada en %.0f min.", wait / 60)
        time.sleep(wait)


if __name__ == "__main__":
    main()
