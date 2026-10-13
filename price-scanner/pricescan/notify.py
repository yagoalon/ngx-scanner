"""Avisos: consola siempre; Telegram y/o ntfy.sh si están configurados por variables de entorno."""
from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger("pricescan")


def send(text: str) -> None:
    print("\n" + text + "\n", flush=True)
    _telegram(text)
    _ntfy(text)


def _telegram(text: str) -> None:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      data={"chat_id": chat, "text": text, "disable_web_page_preview": "true"},
                      timeout=20).raise_for_status()
    except Exception as e:  # noqa: BLE001
        log.warning("Telegram falló: %s", e)


def _ntfy(text: str) -> None:
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        return
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh")
    try:
        requests.post(f"{server}/{topic}", data=text.encode(),
                      headers={"Title": "Oferta GPU / DGX", "Priority": "high"},
                      timeout=20).raise_for_status()
    except Exception as e:  # noqa: BLE001
        log.warning("ntfy falló: %s", e)
