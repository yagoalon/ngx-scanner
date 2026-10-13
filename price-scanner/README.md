# pricescan — vigilante de precios RTX 5090 / DGX Spark (GB10)

Busca en **172 fuentes de 23 países** (Europa + EE. UU.), en su idioma y moneda:

| Tipo | Dónde |
|---|---|
| Google Shopping (SerpAPI) | ES DE FR IT NL AT PT UK US (ampliable a 22 países) |
| Marketplaces | **Amazon** ES DE FR IT NL BE PL SE UK US · **eBay** US ES DE FR IT NL BE AT IE PL CH UK (solo nuevo y "Cómpralo ya") · Allegro PL · eMAG RO HU BG · Kaufland DE CZ PL SK · Bol.com · Cdiscount · Otto |
| EE. UU. | **Walmart**, **Best Buy**, Newegg, B&H, Micro Center, Target, Costco, Adorama, CDW, Central Computers, Dell |
| Comparadores | idealo ES DE FR IT AT UK · Geizhals DE AT EU · billiger.de · Toppreise CH · Trovaprezzi IT · KuantoKusta PT · Tweakers / Kieskeurig NL · Ceneo PL · Heureka CZ SK · Árukereső HU · Compari RO · Skroutz GR · PriceRunner SE DK UK · Prisjakt SE NO FI |
| España / Portugal | PcComponentes, Coolmod, Neobyte, Wipoid, Aussar, Fnac, El Corte Inglés, Worten ES PT, MediaMarkt, Globaldata, PCDiga |
| Alemania / Austria / Suiza | Mindfactory, Caseking, Notebooksbilliger, Computeruniverse, Cyberport DE AT, MediaMarkt / Saturn, Galaxus, Digitec, Brack |
| Francia / Italia / Benelux | LDLC, Materiel.net, Top Achat, Fnac, Boulanger, Grosbill, ePRICE, Unieuro, MediaWorld, Coolblue NL BE, Megekko, Azerty, Alternate ES DE NL BE FR AT |
| Este / Nórdicos / UK | x-kom, Morele, Komputronik, Alza CZ SK HU AT DE, CZC, PC Garage · Proshop DE AT DK SE NO FI PL, Komplett SE NO DK IE, Inet, Webhallen, Elgiganten / Elkjøp / Gigantti, Verkkokauppa, Jimm's · Scan, Overclockers, Ebuyer, CCL, Currys |
| Oficiales | NVIDIA Marketplace ES DE FR IT UK US · Dell (Pro Max GB10) ES DE FR IT UK |

Los anuncios usados, reacondicionados, "solo caja", "para piezas" o de alquiler se descartan en 15 idiomas (`common_exclude`), algo clave en eBay, Walmart y Allegro.

Productos:

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

Necesitas **Python 3.10 o superior** ([python.org](https://www.python.org/downloads/); en Windows marca "Add python.exe to PATH" al instalar).

**Windows (PowerShell):**

```powershell
cd price-scanner
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt playwright
python -m playwright install chromium
copy .env.example .env      # y edítalo con el Bloc de notas
```

**macOS / Linux:**

```bash
cd price-scanner
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt playwright
python -m playwright install chromium
cp .env.example .env        # y edítalo
```

Playwright (Chromium) hace falta para las tiendas con `render: true` (PcComponentes, Amazon, Walmart, Best Buy, NVIDIA…). Sin él, esas fuentes fallan y el resto funciona igual.

Las claves (Telegram, ntfy, SerpAPI) van en el archivo `.env`, junto a `config.yaml`. Todas son opcionales.

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

```
SERPAPI_KEY=tu_clave        # en .env
```

Sin clave esa fuente simplemente se salta y se usan las demás.

## Avisos al móvil

Pon los valores en `.env`:

**Telegram:** habla con @BotFather → `/newbot` → te da el token. Escribe algo a tu bot y luego a @userinfobot para saber tu chat id:

```
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=123456789
```

**ntfy** (más fácil, sin registro): instala la app ntfy en el móvil, suscríbete a un tema con nombre difícil de adivinar y pon el mismo nombre:

```
NTFY_TOPIC=gpu-chollos-x7k2q
```

## Ajustar umbrales y tiendas

Todo está en `config.yaml` (se relee en cada pasada, puedes editarlo con `--loop` en marcha):

- `max_price` → precio a partir del cual avisa. Por defecto 2.400 € la 5090 (la FE salió a 2.369 €) y 3.800 € los GB10 (DGX Spark FE: 3.999 $; versiones de 1 TB de socios desde ~2.999 $). **Son estimaciones: ajústalas.**
- `min_price` → por debajo se marca como ⚠️ SOSPECHOSO y no avisa (suelen ser accesorios o estafas de marketplace).
- `exclude` → palabras que descartan un resultado.
- Para añadir una tienda: copia un bloque `type: search` con su URL de búsqueda usando `{query}`. Si está en varios países, usa `variants:` (mira Amazon o eBay en `config.yaml`). El extractor lee automáticamente los datos schema.org (JSON-LD/microdatos) que llevan casi todas las tiendas, y si no, usa una heurística (enlace del producto + precio más cercano). Si una tienda da 0 resultados, prueba `render: true` o define `selectors` (ver el ejemplo de Amazon).
- Para vigilar una ficha concreta (p. ej. la página de un modelo en Dell o NVIDIA), usa `type: page` con `urls:`.

## Ejecutarlo de forma automática

Lo más sencillo: deja una ventana abierta con `python -m pricescan --loop 30`.

**Windows (Programador de tareas)**, para que arranque solo al iniciar sesión:

```powershell
schtasks /create /tn pricescan /sc onlogon /tr "cmd /c cd /d C:\ruta\price-scanner && .venv\Scripts\python -m pricescan --loop 30 >> pricescan.log 2>&1"
```

**macOS / Linux (cron)**, cada 30 min:

```cron
*/30 * * * * cd /ruta/price-scanner && .venv/bin/python -m pricescan >> pricescan.log 2>&1
```

Conviene ejecutarlo desde casa (IP residencial): desde servidores en la nube muchas tiendas devuelven 403. Las tiendas se consultan en paralelo (`parallel: 8` con HTTP normal y `parallel_browsers: 3` navegadores para las 68 fuentes con `render: true`), con 2–5 s de pausa entre peticiones a la misma tienda. Una pasada completa tarda unos 20–30 min. Para ir más rápido, quita países o tiendas con `enabled: false`, o recorta `shop_queries`.

## Comprar fuera de España

- **UE**: mismo IVA incluido, garantía europea, sin aduana. Mira que la tienda envíe a España (Mindfactory, por ejemplo, solo envía a Alemania; Caseking, Alternate, Proshop, LDLC y Amazon sí).
- **eBay / Walmart / Allegro (marketplaces)**: comprueba la valoración del vendedor. Un precio por debajo de `min_price` se marca como ⚠️ sospechoso y no avisa.
- **EE. UU.**: muchas tiendas no envían fuera; a menudo hace falta un reenviador. Pagarás el IVA al importar y la garantía puede ser solo en EE. UU. Ajusta `landing.US` a tu caso.
- **UK / Suiza**: fuera de la UE, hay aduana. Los factores de `landing` son aproximados.

## Tests

```bash
pip install pytest && python -m pytest -q
```

## Notas

- Respeta los términos de cada tienda; el programa espera 2–5 s entre peticiones.
- Los selectores/URLs de las tiendas cambian con el tiempo: si una fuente deja de devolver resultados, revisa su URL de búsqueda.
