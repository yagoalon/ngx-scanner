"""Reglas para decidir si un título corresponde a un producto vigilado y si el precio es bueno."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return f" {text.strip()} "


def _has(norm_title: str, term: str) -> bool:
    return normalize(term) in norm_title


@dataclass
class Product:
    id: str
    name: str
    max_price: float                     # precio "bueno" (≈ lanzamiento) en EUR
    min_price: float = 0                 # por debajo: casi seguro accesorio / estafa
    steal_price: float = 0               # "ganga": precio extremadamente bueno → aviso urgente
    require_all: list[list[str]] = field(default_factory=list)  # cada grupo: al menos uno
    exclude: list[str] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)            # búsquedas a lanzar

    @classmethod
    def from_dict(cls, d: dict) -> "Product":
        groups = [g if isinstance(g, list) else [g] for g in d.get("require_all", [])]
        return cls(
            id=d["id"], name=d.get("name", d["id"]),
            max_price=float(d["max_price"]), min_price=float(d.get("min_price", 0)),
            steal_price=float(d.get("steal_price", 0)),
            require_all=groups, exclude=d.get("exclude", []),
            queries=d.get("queries", [d.get("name", d["id"])]),
        )

    def matches(self, title: str) -> bool:
        t = normalize(title)
        if any(_has(t, x) for x in self.exclude):
            return False
        return all(any(_has(t, term) for term in group) for group in self.require_all)

    def verdict(self, price: float) -> str | None:
        """'steal' (ganga), 'deal' (buen precio), 'suspicious' (demasiado barato) o None."""
        if price < self.min_price:
            return "suspicious"
        if price <= self.steal_price:
            return "steal"
        if price <= self.max_price:
            return "deal"
        return None


def classify(title: str, products: list[Product]) -> Product | None:
    for p in products:
        if p.matches(title):
            return p
    return None
