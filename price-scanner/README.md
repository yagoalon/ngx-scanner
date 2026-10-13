# pricescan — vigilante de precios RTX 5090 / DGX Spark (GB10)

Busca en Google Shopping (cientos de tiendas), comparadores y tiendas concretas:

- **GeForce RTX 5090 32 GB** (cualquier marca), descartando portátiles, PCs montados, la 5090 D china (24 GB), bloques de agua, cables, reacondicionados…
- **NVIDIA DGX Spark y equipos GB10 de otras marcas**: Dell Pro Max GB10, ASUS Ascent GX10, Lenovo ThinkStation PGX, MSI EdgeXpert, Acer Veriton GN100, HP ZGX Nano, Gigabyte AI TOP Atom.

Te avisa (consola, Telegram o ntfy en el móvil) cuando encuentra uno **por debajo de tu umbral** (por defecto ≈ precio de lanzamiento) y solo **otra vez si baja de precio**, para no llenarte de mensajes repetidos.

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

## Cobertura de "toda la web": SerpAPI (recomendado)

Las tiendas grandes bloquean los scrapers. La forma fiable de cubrir todo es Google Shopping a través de [SerpAPI](https://serpapi.com) (el plan gratuito da 100 búsquedas/mes; cada pasada usa 8, una por cada `queries` de `config.yaml`, así que con el plan gratuito da para ~12 pasadas al mes: recorta las `queries` o usa un plan de pago si quieres más frecuencia):

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

Conviene ejecutarlo desde casa (IP residencial): desde servidores en la nube muchas tiendas devuelven 403.

## Tests

```bash
pip install pytest && python -m pytest -q
```

## Notas

- Respeta los términos de cada tienda; el programa espera 2–5 s entre peticiones.
- Los selectores/URLs de las tiendas cambian con el tiempo: si una fuente deja de devolver resultados, revisa su URL de búsqueda.
