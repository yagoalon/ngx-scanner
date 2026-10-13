"""Tipos de cambio a EUR: tabla diaria del BCE, con la de config.yaml como respaldo."""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

import requests

log = logging.getLogger("pricescan")
ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"


def eur_rates(fallback: dict) -> dict[str, float]:
    """→ {moneda: euros por unidad}. P. ej. {'USD': 0.86, 'GBP': 1.15}."""
    rates = {k.upper(): float(v) for k, v in (fallback or {}).items()}
    try:
        r = requests.get(ECB_URL, timeout=15)
        r.raise_for_status()
        for node in ET.fromstring(r.content).iter():
            if node.get("currency") and node.get("rate"):
                rates[node.get("currency")] = 1 / float(node.get("rate"))
    except Exception as e:  # noqa: BLE001
        log.info("Sin cambio del BCE (%s); uso fx_to_eur de config.yaml.", e)
    rates["EUR"] = 1.0
    return rates
