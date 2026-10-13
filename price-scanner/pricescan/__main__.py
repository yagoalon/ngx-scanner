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
from datetime import datetime
from pathlib import Path

import yaml

from . import notify
from .extract import Offer, dedupe
from .products import Product, classify
from .sources import RUNNERS, Fetcher

log = logging.getLogger("pricescan")


def load_config(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def to_eur(offer: Offer, fx: dict) -> float | None:
    if offer.currency in ("EUR", ""):
        return offer.price
    rate = fx.get(offer.currency.upper())
    return offer.price * rate if rate else None


def scan(cfg: dict) -> list[tuple[Product, Offer, float]]:
    products = [Product.from_dict(p) for p in cfg["products"]]
    fetcher = Fetcher(delay=tuple(cfg.get("delay_seconds", [2, 5])))
    raw: list[Offer] = []
    try:
        for src in cfg.get("sources", []):
            if src.get("enabled", True) is False:
                continue
            runner = RUNNERS[src["type"]]
            got = runner(src, fetcher, products)
            log.info("%-28s %3d ofertas", src.get("name", src["type"]), len(got))
            raw += got
    finally:
        fetcher.close()

    results = []
    fx = {k.upper(): v for k, v in cfg.get("fx_to_eur", {}).items()}
    for offer in dedupe(raw):
        if offer.in_stock is False and not cfg.get("include_out_of_stock", False):
            continue
        product = classify(offer.title, products)
        eur = to_eur(offer, fx)
        if product and eur:
            results.append((product, offer, round(eur, 2)))
    results.sort(key=lambda r: (r[0].id, r[2]))
    return results


def load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def report(results, cfg: dict, show_all: bool) -> None:
    state_path = Path(cfg.get("state_file", "state.json"))
    state = load_state(state_path)
    alerts = []
    for product, offer, eur in results:
        verdict = product.verdict(eur)
        prev = state.get(offer.key(), {}).get("price")
        state[offer.key()] = {"price": eur, "title": offer.title, "seen": datetime.now().isoformat(timespec="minutes")}
        if show_all or verdict:
            tag = {"deal": "🔥 CHOLLO", "suspicious": "⚠️ SOSPECHOSO"}.get(verdict, "   ")
            print(f"{tag:12} {eur:9.2f} €  [{product.id}] {offer.shop:22.22} {offer.title[:80]}\n{'':14}{offer.url}")
        # Avisar sólo si es chollo y es nuevo o ha bajado de precio.
        if verdict == "deal" and (prev is None or eur < prev - 0.5):
            delta = f" (antes {prev:.0f} €)" if prev else ""
            alerts.append(f"🔥 {product.name}: {eur:.2f} €{delta} — umbral {product.max_price:.0f} €\n"
                          f"{offer.title}\n{offer.shop}\n{offer.url}")
    state_path.write_text(json.dumps(state, indent=1, ensure_ascii=False))

    if out := cfg.get("csv_file"):
        new = not Path(out).exists()
        with open(out, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["fecha", "producto", "precio_eur", "tienda", "titulo", "url"])
            now = datetime.now().isoformat(timespec="minutes")
            for product, offer, eur in results:
                w.writerow([now, product.id, eur, offer.shop, offer.title, offer.url])

    log.info("%d ofertas relevantes, %d avisos nuevos.", len(results), len(alerts))
    for text in alerts:
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
        report(scan(cfg), cfg, args.all)
        if not args.loop:
            break
        wait = args.loop * 60 * random.uniform(0.85, 1.15)
        log.info("Siguiente pasada en %.0f min.", wait / 60)
        time.sleep(wait)


if __name__ == "__main__":
    main()
