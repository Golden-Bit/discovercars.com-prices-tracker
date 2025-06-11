#!/usr/bin/env python3
"""
discovercars_details_playwright.py
──────────────────────────────────
Arricchisce con **tutti i dettagli** le auto già raccolte da
`discovercars_playwright.py`.

● Legge `cars.json` dentro una cartella di lavoro (WORK_DIR).
● Visita ogni link, estrae tutti i campi utili e salva
  `cars_details.json` nella *stessa* cartella.

> La cartella di lavoro è la stessa generata dal primo script:
>    "<slug_location>_<pick_date>/"
> Puoi cambiarla impostando la variabile **WORK_DIR** qui sotto
> oppure passandola come primo argomento da CLI.

Prerequisiti
------------
    pip install playwright
    playwright install
"""

from __future__ import annotations

import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import TimeoutError as TE, sync_playwright

from step_1 import _slugify


SETTINGS = json.load(open("global_params.json", "r"))


# ----------------------------------------------------------------------------
# CONFIGURAZIONE -------------------------------------------------------------
# ----------------------------------------------------------------------------

# --- imposta la directory di lavoro (cartella con i JSON) ------------------
SETTINGS = json.load(open("global_params.json", "r"))
location  = SETTINGS["location"]
pick_date = SETTINGS["pick_date"]
drop_date = SETTINGS["drop_date"]

# ――― Calcolo del periodo in giorni ―――
fmt = "%Y-%m-%d"
dt_pick = datetime.strptime(pick_date, fmt)
dt_drop = datetime.strptime(drop_date, fmt)
period_days = (dt_drop - dt_pick).days

slug_loc = _slugify(location)
WORK_DIR = Path("data") / slug_loc / str(period_days) / pick_date
WORK_DIR = WORK_DIR.resolve()

# Override da CLI (opzionale)
if len(sys.argv) > 1:
    WORK_DIR = Path(sys.argv[1]).expanduser().resolve()
WORK_DIR.mkdir(parents=True, exist_ok=True)

SRC_FILE  = WORK_DIR / "cars.json"
DEST_FILE = WORK_DIR / "cars_details.json"

# range di record da processare (inclusivo / esclusivo)
START_INDEX = 0
END_INDEX = 999

# ----------------------------------------------------------------------------
# helper stringa → float -----------------------------------------------------
# ----------------------------------------------------------------------------
_CURRENCY_RE = re.compile(r"[€$,]")


def _price_to_float(text: str | None) -> float | None:
    if not text:
        return None
    try:
        return float(_CURRENCY_RE.sub("", text).strip())
    except ValueError:
        return None


def _safe_text(locator) -> str:
    """Restituisce il testo del locator, oppure '' se non trovato."""
    try:
        return locator.first.inner_text().strip()
    except TE:
        return ""


# ----------------------------------------------------------------------------
# parsing pagina singola -----------------------------------------------------
# ----------------------------------------------------------------------------
def parse_car_page(page) -> dict:
    """Estrae attributi dalla pagina veicolo."""
    data: dict = {}

    # blocco pick-up / drop-off
    data["pickup_datetime"] = _safe_text(page.locator(".lb-datetime"))
    data["dropoff_datetime"] = _safe_text(page.locator(".lb-datetime").nth(1))
    data["pickup_location"] = _safe_text(page.locator(".lb-position"))
    data["pickup_address"] = _safe_text(page.locator(".lb-address"))
    data["pickup_instructions"] = _safe_text(
        page.locator(".supplier-info-block.instruction .data-value")
    )

    # info auto base
    car_name_full = _safe_text(page.locator(".car-name"))
    data["category"] = car_name_full.split()[0] if car_name_full else ""
    data["model"] = _safe_text(page.locator(".car-name .car-similar"))

    specs = page.locator(".car-params span").all_inner_texts()
    for spec in specs:
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

    # badge e premi
    data["badges"] = [b.strip() for b in page.locator(".dc-ui.badge").all_inner_texts()]

    # fornitore
    data["supplier_name"] = page.locator(
        ".supplier-logo-and-rating-block img"
    ).first.get_attribute("alt")
    try:
        data["supplier_rating"] = float(
            page.locator(".supplier-rating-block .text-bold").first.inner_text()
        )
    except (TE, ValueError):
        data["supplier_rating"] = None
    data["supplier_rating_label"] = _safe_text(
        page.locator(".supplier-rating-data .text-16")
    )

    # fuel policy / shuttle
    fp = page.locator(".supplier-info-block.fuel-policy .data-value")
    if fp.count():
        data["fuel_policy"] = fp.first.inner_text().strip()
    pl = page.locator(".supplier-info-block.pickup-location .data-value")
    if pl.count():
        data["pickup_mode"] = pl.first.inner_text().strip()

    # extras inclusi
    data["included_extras"] = [
        html.unescape(x).strip()
        for x in page.locator(".free-extras li:not(.more-less) span").all_inner_texts()
    ]

    # price breakdown
    summary = {}
    for item in page.locator("#b-price-summary .summary-item").all():
        label = item.inner_text().splitlines()[-1].strip()
        summary[label] = _price_to_float(item.get_attribute("data-price"))
    summary["Total"] = _price_to_float(_safe_text(page.locator("#total-sum")))
    data["price_breakdown"] = summary

    data["pay_now"] = _price_to_float(_safe_text(page.locator("#amount-payable-now")))
    data["pay_on_arrival"] = _price_to_float(
        _safe_text(page.locator("#amount-payable-on-arrival"))
    )

    return data


# ----------------------------------------------------------------------------
# MAIN -----------------------------------------------------------------------
# ----------------------------------------------------------------------------
def main():
    if not SRC_FILE.exists():
        sys.exit(f"Errore: '{SRC_FILE}' non trovato. Esegui prima lo scraper base.")

    cars = json.loads(SRC_FILE.read_text(encoding="utf-8"))["cars"]
    subset = cars[START_INDEX:END_INDEX] if END_INDEX else cars[START_INDEX:]

    details = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        for i, car in enumerate(subset, start=START_INDEX):
            url = car["link"]
            print(f"[{i}] fetch → {url}")
            try:
                page.goto(url, timeout=45_000)
                page.wait_for_load_state("networkidle")
                details.append({**car, **parse_car_page(page)})
            except TE:
                print("   timeout — skipped")
        browser.close()

    DEST_FILE.write_text(json.dumps(details, ensure_ascii=False, indent=2), "utf-8")
    print(f"\n✓ Salvati {len(details)} record in {DEST_FILE}\n")


if __name__ == "__main__":
    main()
