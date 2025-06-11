#!/usr/bin/env python3
"""
select_and_scrape_grouped_cars.py   –  versione “threshold + regole”
────────────────────────────────────────────────────────────────────
Per ciascun gruppo in `gruppi_sipp.json`:

1.   Considera SOLO i modelli con score ≥ SOGLIA_SCORE (default 0.9).
2.   Raccoglie **tutte** le offerte per quei modelli in `cars.json`,
     le ordina per prezzo crescente.
3.   Scorre le offerte finché trova la prima che soddisfa **in quest’ordine**:
     a) il supplier è quello preferito (PREFERRED_SUPPLIER)
        **oppure**
     b) la trasmissione dell’offerta coincide con la trasmissione del gruppo
        (“MANUAL” / “AUTOMATIC”).
4.   Visita la pagina dell’offerta prescelta, estrae i dettagli completi
     (funzione `parse_car_page`).
5.   Scrive `group_selected_details.json` con, per ogni gruppo,
     `selected_car_details` → dettagli dell’auto scelta (o `null` se nessuna
     offerta soddisfa i criteri).

Il criterio “supplier preferito” viene valutato **prima** di quello sul
cambio; se non si trova il supplier giusto, si passa al test sul cambio.

"""

from __future__ import annotations

import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from playwright.sync_api import TimeoutError as TE, sync_playwright

# ────────────────────────────────────────────────────────────────────────────
# PARAMETRI CONFIGURABILI
# ────────────────────────────────────────────────────────────────────────────
SOGLIA_SCORE       = 0.9               # score minimo per considerare un modello
EXCLUDE_SUPPLIERS = ["Sicily By Car"]   # cambia a piacere (case-insensitive)

# ────────────────────────────────────────────────────────────────────────────
#  SLUG + PATH HELPERS
# ────────────────────────────────────────────────────────────────────────────
def _slugify(t: str) -> str:
    import unicodedata, re
    return re.sub(r"[^\w]+", "_",
                  unicodedata.normalize("NFKD", t).encode("ascii", "ignore")
                  .decode()).strip("_").lower()

# ────────────────────────────────────────────────────────────────────────────
#  PARSER PAGINA DETTAGLIO  (stessa logica dello step 4)
# ────────────────────────────────────────────────────────────────────────────
_CURRENCY_RE = re.compile(r"[€$,]")

def _price_to_float(txt: str | None) -> float | None:
    if not txt:
        return None
    try:
        return float(_CURRENCY_RE.sub("", txt).strip())
    except ValueError:
        return None

def _safe_text(locator) -> str:
    try:
        return locator.first.inner_text().strip()
    except TE:
        return ""

def parse_car_page(page) -> Dict:
    data: Dict = {}

    data["pickup_datetime"]     = _safe_text(page.locator(".lb-datetime"))
    data["dropoff_datetime"]    = _safe_text(page.locator(".lb-datetime").nth(1))
    data["pickup_location"]     = _safe_text(page.locator(".lb-position"))
    data["pickup_address"]      = _safe_text(page.locator(".lb-address"))
    data["pickup_instructions"] = _safe_text(
        page.locator(".supplier-info-block.instruction .data-value"))

    car_name_full  = _safe_text(page.locator(".car-name"))
    data["category"] = car_name_full.split()[0] if car_name_full else ""
    data["model"]    = _safe_text(page.locator(".car-name .car-similar"))

    for spec in page.locator(".car-params span").all_inner_texts():
        if "seats" in spec:
            data["seats"] = int(re.search(r"\d+", spec).group())
        elif "bags" in spec:
            data["bags"] = int(re.search(r"\d+", spec).group())
        elif "doors" in spec:
            data["doors"] = int(re.search(r"\d+", spec).group())
        elif "Automatic" in spec or "Manual" in spec:
            data["transmission"] = spec.strip()
        elif "Air Conditioning" in spec:
            data["air_conditioning"] = True

    data["badges"] = [b.strip() for b in page.locator(".dc-ui.badge").all_inner_texts()]

    data["supplier_name"] = _safe_text(
        page.locator(".supplier-logo-and-rating-block img").first
    )
    try:
        data["supplier_rating"] = float(
            page.locator(".supplier-rating-block .text-bold").first.inner_text())
    except (TE, ValueError):
        data["supplier_rating"] = None
    data["supplier_rating_label"] = _safe_text(
        page.locator(".supplier-rating-data .text-16"))

    if (fp := page.locator(".supplier-info-block.fuel-policy .data-value")).count():
        data["fuel_policy"] = fp.first.inner_text().strip()
    if (pl := page.locator(".supplier-info-block.pickup-location .data-value")).count():
        data["pickup_mode"] = pl.first.inner_text().strip()

    data["included_extras"] = [
        html.unescape(x).strip()
        for x in page.locator(".free-extras li:not(.more-less) span").all_inner_texts()
    ]

    summary = {}
    for item in page.locator("#b-price-summary .summary-item").all():
        lbl = item.inner_text().splitlines()[-1].strip()
        summary[lbl] = _price_to_float(item.get_attribute("data-price"))
    summary["Total"] = _price_to_float(_safe_text(page.locator("#total-sum")))
    data["price_breakdown"] = summary

    data["pay_now"]        = _price_to_float(_safe_text(page.locator("#amount-payable-now")))
    data["pay_on_arrival"] = _price_to_float(_safe_text(page.locator("#amount-payable-on-arrival")))

    return data

# ────────────────────────────────────────────────────────────────────────────
#  PROCEDURA PRINCIPALE
# ────────────────────────────────────────────────────────────────────────────
def main(settings_path: str = "global_params.json"):

    settings = json.loads(Path(settings_path).read_text(encoding="utf-8"))
    loc, p_d, d_d = settings["location"], settings["pick_date"], settings["drop_date"]
    period = (datetime.strptime(d_d, "%Y-%m-%d") - datetime.strptime(p_d, "%Y-%m-%d")).days
    work_dir = Path("data") / _slugify(loc) / str(period) / p_d

    gruppi_path = work_dir / "gruppi_sipp.json"
    cars_path   = work_dir / "cars.json"
    out_path    = work_dir / "group_selected_details.json"

    if not gruppi_path.exists() or not cars_path.exists():
        sys.exit("File di input mancanti: eseguire step precedenti.")

    gruppi = json.loads(gruppi_path.read_text(encoding="utf-8"))
    cars   = json.loads(cars_path.read_text(encoding="utf-8"))["cars"]

    # — indicizzazione offerte per modello —
    offers_by_model: Dict[str, List[Dict]] = {}
    for car in cars:
        mdl = car["name"].strip()
        offers_by_model.setdefault(mdl, []).append(car)

    # pre-ordina ciascuna lista per prezzo (None → ∞)
    for lst in offers_by_model.values():
        lst.sort(key=lambda e: e["price_eur"] if e["price_eur"] is not None else float("inf"))

    output: List[Dict] = []

    print("▶ Avvio scraping selettivo…")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()

        for g in gruppi:
            print(g)
            g_out = g.copy()
            g_out["selected_car_details"] = None

            # 1. filtra modelli con score ≥ SOGLIA_SCORE
            candidate_models = [
                v["model"] for v in g.get("vehicles", [])
                if v.get("score", 0) >= SOGLIA_SCORE
            ]

            if not candidate_models:
                output.append(g_out)
                continue

            # 2. produce lista di offerte (pre-ordinate) tra tutti i candidati
            offers: List[Dict] = []
            for mdl in candidate_models:
                offers.extend(offers_by_model.get(mdl, []))
            offers.sort(key=lambda e: e["price_eur"] if e["price_eur"] is not None else float("inf"))

            # 3. scorre le offerte finché trova quella che rispetta le regole
            for off in offers:
                print(off)
                link  = off["link"]
                price = off["price_eur"]
                try:
                    page.goto(link, timeout=45_000)
                    page.wait_for_load_state("networkidle")
                except TE:
                    continue  # timeout: prova offerta successiva
                print("**")

                # >>>>>>>>>>>  NUOVO BLOCCO  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
                # 1. rileva redirect verso pagina /search/
                redir_url = page.url.split("?", 1)[0]  # rimuovo parametri GET
                if "/search/" in redir_url:
                    print(f"  ↳ link obsoleto, redirect a pagina search: {redir_url}")
                    continue  # salto: passo all’offerta successiva

                # 2. extra-guard: se per qualche motivo non c’è il selettore .car-name
                if not page.locator(".car-name").count():
                    print("  ↳ nessun dettagli veicolo, salto.")
                    continue
                # >>>>>>>>>>>  FINE NUOVO BLOCCO  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

                details = parse_car_page(page)
                print("**")
                supplier_ok = details.get("supplier_name", "").lower() not in EXCLUDE_SUPPLIERS
                transm = details.get("transmission", "").upper()
                group_transm = g.get("transmission", "").upper()
                transm_ok = group_transm in transm if group_transm else True

                # scelta in base alle regole
                if supplier_ok and transm_ok:
                    g_out["selected_car_details"] = {
                        "model": off["name"].strip(),
                        "link":  link,
                        "price_eur": price,
                        "price_text": off.get("price_text", ""),
                        **details
                    }
                    break  # stop: trovato veicolo valido

            output.append(g_out)

        browser.close()

    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ Dettagli scritti in '{out_path}'")


# ----------------------------------------------------------------------------
if __name__ == "__main__":
    main()
