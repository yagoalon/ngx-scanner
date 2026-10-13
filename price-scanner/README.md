# pricescan — vigilante de precios RTX 5090 / DGX Spark (GB10)

Busca en **toda Europa y EE. UU.**: Google Shopping de 9 países (ampliable a 22), comparadores (idealo ES/DE/FR/IT/AT/UK, Geizhals, Tweakers, Ceneo) y tiendas (PcComponentes, Mindfactory, Caseking, Alternate, LDLC, Materiel.net, Scan, Overclockers, Amazon ES/DE/FR/IT/US, Newegg, B&H, Micro Center, Best Buy, NVIDIA Marketplace…):

- **GeForce RTX 5090 32 GB** (cualquier marca), descartando portátiles, PCs montados, la 5090 D china (24 GB), bloques de agua, cables, reacondicionados…
- **NVIDIA DGX Spark y equipos GB10 de otras marcas**: Dell Pro Max GB10, ASUS Ascent GX10, Lenovo ThinkStation PGX, MSI EdgeXpert, Acer Veriton GN100, HP ZGX Nano, Gigabyte AI TOP Atom.

Te avisa (consola, Telegram o ntfy en el móvil) con tres niveles:

| Aviso | Cuándo | 5090 | GB10 |
|---|---|---|---|
| 🚨 **GANGA** | precio extremadamente bueno (`steal_price`) | ≤ 2.000 € | ≤ 3.000 € |
| ⏳ **ÚLTIMAS UNIDADES** | la tienda dice "últimas unidades", "only 2 left", "nur noch 1", "plus que 2"… (ES/EN/DE/FR/IT/PT/NL/PL) o `LimitedAvailability` | — | — |
| 🔥 **Buen precio** | ≈ precio de lanzamiento (`max_price`) | ≤ 2.400 € | ≤ 3.800 € |

Los precios se comparan siempre con el **coste puesto en casa en EUR**: se convierte la moneda (cambio diario del BCE) y, para tiendas de otro país, se suma una estimación de IVA de importación y envío (EE. UU.: +21 % IVA + 80 €; ver `landing` en `config.yaml`). Así una 5090 FE de 1.999 $ en EE. UU. aparece como ≈2.160 € y se puede comparar directamente con una tienda alemana.

Solo vuelve a avisar del mismo producto si **baja de precio** o si **pasa a últimas unidades**. Con `notify_deals: false` solo recibes gangas y últimas unidades a buen precio.

## Instalación

```bash
cd price-scanner
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Opcional (PcComponentes, Amazon, NVIDIA usan JavaScript/anti-bot):
pip install playwright && python -m playwright install chromium
```

## Uso

```bash
python -m pricescan              # una pasada
python -m pricescan --all        # ver todo lo encontrado, no solo chollos
python -m pricescan --loop 30    # repetir cada ~30 min (con variación aleatoria)
```

Salida de ejemplo:

```
🔥 CHOLLO     2349.90 €  [rtx5090] pccomponentes.com      MSI GeForce RTX 5090 Ventus 3X OC 32GB GDDR7
              https://www.pccomponentes.com/...
```

Todo lo visto se guarda en `historial.csv` para ver la evolución de precios.

## Cobertura de toda Europa + EE. UU.: SerpAPI (recomendado)

Las tiendas grandes bloquean los scrapers. La forma fiable de cubrirlo todo es Google Shopping a través de [SerpAPI](https://serpapi.com), país por país (`countries:` en `config.yaml`; disponibles: es, pt, fr, de, at, it, nl, be, ie, fi, gr, sk, pl, cz, se, dk, no, hu, ro, ch, gb, us).

Coste: cada pasada gasta **países × queries** búsquedas (por defecto 9 × 3 = 27) y se lanza como mucho cada `every_minutes: 360` (4 veces al día ≈ 3.200 búsquedas/mes). El plan gratuito (100/mes) no llega: para usarlo gratis deja 1–2 países y sube `every_minutes`. Las demás fuentes (comparadores y tiendas) son gratis.

```bash
export SERPAPI_KEY=tu_clave
```

Sin clave esa fuente simplemente se salta y se usan las demás.

## Avisos al móvil

**Telegram:** crea un bot con @BotFather y obtén tu chat id (p. ej. escribiendo a @userinfobot):

```bash
export TELEGRAM_BOT_TOKEN=123456:ABC...
export TELEGRAM_CHAT_ID=123456789
```

**ntfy** (sin registro): instala la app ntfy, suscríbete a un tema con nombre difícil de adivinar y:

```bash
export NTFY_TOPIC=gpu-chollos-x7k2q
```

## Ajustar umbrales y tiendas

Todo está en `config.yaml` (se relee en cada pasada, puedes editarlo con `--loop` en marcha):

- `max_price` → precio a partir del cual avisa. Por defecto 2.400 € la 5090 (la FE salió a 2.369 €) y 3.800 € los GB10 (DGX Spark FE: 3.999 $; versiones de 1 TB de socios desde ~2.999 $). **Son estimaciones: ajústalas.**
- `min_price` → por debajo se marca como ⚠️ SOSPECHOSO y no avisa (suelen ser accesorios o estafas de marketplace).
- `exclude` → palabras que descartan un resultado.
- Para añadir una tienda: copia un bloque `type: search` con su URL de búsqueda usando `{query}`. El extractor lee automáticamente los datos schema.org (JSON-LD/microdatos) que llevan casi todas las tiendas, y si no, usa una heurística (enlace del producto + precio más cercano). Si una tienda da 0 resultados, prueba `render: true` o define `selectors` (ver el ejemplo de Amazon).
- Para vigilar una ficha concreta (p. ej. la página de un modelo en Dell o NVIDIA), usa `type: page` con `urls:`.

## Ejecutarlo de forma automática

Con cron (cada 30 min):

```cron
*/30 * * * * cd /ruta/price-scanner && .venv/bin/python -m pricescan >> pricescan.log 2>&1
```

Conviene ejecutarlo desde casa (IP residencial): desde servidores en la nube muchas tiendas devuelven 403. Una pasada completa con todas las fuentes tarda unos 15–20 min (2–5 s de pausa entre peticiones); desactiva con `enabled: false` las que no te interesen.

## Comprar fuera de España

- **UE**: mismo IVA incluido, garantía europea, sin aduana. Mira que la tienda envíe a España (Mindfactory, por ejemplo, solo envía a Alemania; Caseking, Alternate, Proshop, LDLC y Amazon sí).
- **EE. UU.**: muchas tiendas no envían fuera; a menudo hace falta un reenviador. Pagarás el IVA al importar y la garantía puede ser solo en EE. UU. Ajusta `landing.US` a tu caso.
- **UK / Suiza**: fuera de la UE, hay aduana. Los factores de `landing` son aproximados.

## Tests

```bash
pip install pytest && python -m pytest -q
```

## Notas

- Respeta los términos de cada tienda; el programa espera 2–5 s entre peticiones.
- Los selectores/URLs de las tiendas cambian con el tiempo: si una fuente deja de devolver resultados, revisa su URL de búsqueda.
