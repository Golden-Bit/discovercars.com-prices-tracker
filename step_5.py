#!/usr/bin/env python3
"""
select_and_scrape_grouped_cars.py
──────────────────────────────────
Legge il file `gruppi_sipp.json` e il file `cars.json` dalla directory
dedotta dai parametri globali. Per ciascun gruppo in `gruppi_sipp.json`:
  1. Seleziona il modello con punteggio più alto.
  2. Cerca tutte le occorrenze di quel modello in `cars.json` e ne sceglie
     quella con prezzo minimo.
  3. Visita il link corrispondente alla macchina selezionata, estrae tutti
     i dettagli come in `discovercars_details_playwright.py` e li associa
     al gruppo.
Produce un JSON di output (`group_selected_details.json`) contenente, per
ogni gruppo, tutti i campi originali del gruppo e un campo aggiuntivo
`"selected_car_details"` con tutte le informazioni del veicolo scelto.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin
import html
from playwright.sync_api import TimeoutError as TE, sync_playwright

# ────────────────────────────────────────────────────────────────────────────
# HELPERS PER IL CALCOLO DI WORK_DIR
# ────────────────────────────────────────────────────────────────────────────

def _slugify(text: str) -> str:
    import unicodedata
    norm = unicodedata.normalize("NFKD", text)
    ascii_txt = norm.encode("ascii", "ignore").decode()
    slug = re.sub(r"[^\w]+", "_", ascii_txt).strip("_").lower()
    return slug

# ────────────────────────────────────────────────────────────────────────────
# HELPERS PER LO SCRAPING DEI DETTAGLI DELL’AUTO
# ────────────────────────────────────────────────────────────────────────────

_CURRENCY_RE = re.compile(r"[€$,]")

def _price_to_float(text: str | None) -> float | None:
    """Rimuove simboli di valuta e converte in float. Se non valido, ritorna None."""
    if not text:
        return None
    try:
        return float(_CURRENCY_RE.sub("", text).strip())
    except ValueError:
        return None

def _safe_text(locator) -> str:
    """Restituisce il testo del primo elemento del locator, o '' se assente."""
    try:
        return locator.first.inner_text().strip()
    except TE:
        return ""

def parse_car_page(page) -> dict:
    """
    Estrae tutti i dettagli dalla pagina di dettaglio del veicolo,
    replicando la logica di `discovercars_details_playwright.py`.
    """
    data: dict = {}

    # blocco pick-up / drop-off
    data["pickup_datetime"]     = _safe_text(page.locator(".lb-datetime"))
    data["dropoff_datetime"]    = _safe_text(page.locator(".lb-datetime").nth(1))
    data["pickup_location"]     = _safe_text(page.locator(".lb-position"))
    data["pickup_address"]      = _safe_text(page.locator(".lb-address"))
    data["pickup_instructions"] = _safe_text(
        page.locator(".supplier-info-block.instruction .data-value")
    )

    # info auto base
    car_name_full = _safe_text(page.locator(".car-name"))
    data["category"] = car_name_full.split()[0] if car_name_full else ""
    data["model"]    = _safe_text(page.locator(".car-name .car-similar"))

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
    data["badges"] = [
        b.strip() for b in page.locator(".dc-ui.badge").all_inner_texts()
    ]

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

    data["pay_now"]        = _price_to_float(_safe_text(page.locator("#amount-payable-now")))
    data["pay_on_arrival"] = _price_to_float(_safe_text(page.locator("#amount-payable-on-arrival")))

    return data

# ────────────────────────────────────────────────────────────────────────────
# FUNZIONE PRINCIPALE
# ────────────────────────────────────────────────────────────────────────────

def step_5(settings: dict):
    location  = settings["location"]
    pick_date = settings["pick_date"]
    drop_date = settings["drop_date"]

    # Calcolo del periodo in giorni
    fmt = "%Y-%m-%d"
    dt_pick = datetime.strptime(pick_date, fmt)
    dt_drop = datetime.strptime(drop_date, fmt)
    period_days = (dt_drop - dt_pick).days

    # Calcolo di WORK_DIR
    slug_loc = _slugify(location)
    work_dir = Path("data") / slug_loc / str(period_days) / pick_date
    work_dir = work_dir.resolve()

    if not work_dir.exists():
        sys.exit(f"Errore: la cartella di lavoro '{work_dir}' non esiste. "
                 f"Esegui prima gli script di scraping per popolarla.")

    # File di input
    GRUPPI_SIPP_FILE = work_dir / "gruppi_sipp.json"
    CARS_FILE        = work_dir / "cars.json"

    if not GRUPPI_SIPP_FILE.exists():
        sys.exit(f"Errore: '{GRUPPI_SIPP_FILE}' non trovato.")
    if not CARS_FILE.exists():
        sys.exit(f"Errore: '{CARS_FILE}' non trovato.")

    # File di output
    OUTPUT_FILE = work_dir / "group_selected_details.json"

    # Carica dati di input
    gruppi = json.loads(GRUPPI_SIPP_FILE.read_text(encoding="utf-8"))
    cars   = json.loads(CARS_FILE.read_text(encoding="utf-8"))["cars"]

    # Costruisco un dizionario per raggruppare in base al nome del modello
    # e trovare il prezzo minimo e link corrispondente.
    # Chiave: nome modello esatto (case-sensitive); valore: dict { "link", "price_eur", "price_text" }
    cars_by_model: dict[str, dict] = {}
    for entry in cars:
        model_name = entry["name"].strip()
        price = entry.get("price_eur")
        if model_name in cars_by_model:
            existing_price = cars_by_model[model_name]["price_eur"]
            # Se prezzo corrente è minore (e non None), sostituisco
            if price is not None and (existing_price is None or price < existing_price):
                cars_by_model[model_name] = {
                    "link": entry["link"],
                    "price_eur": price,
                    "price_text": entry.get("price_text", "")
                }
        else:
            cars_by_model[model_name] = {
                "link": entry["link"],
                "price_eur": price,
                "price_text": entry.get("price_text", "")
            }

    # Preparo lista di output raggruppata
    output_groups: list[dict] = []

    # Avvio Playwright una sola volta fuori dal loop per efficienza
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()

        # Per ogni gruppo, seleziono il veicolo con punteggio più alto
        for grp in gruppi:
            gruppo_output = grp.copy()  # Copia tutti i campi esistenti
            selected_details: dict | None = None

            # Se la lista 'vehicles' esiste e contiene elementi
            vehs = grp.get("vehicles", [])
            if vehs:
                # Trovo punteggio massimo
                max_score = max(v["score"] for v in vehs)
                # Tra quelli con score == max_score, scelgo il primo (ordine originale)
                candidates = [v for v in vehs if v["score"] == max_score]
                best_model = candidates[0]["model"]  # nome modello

                # Cerco il link e il prezzo minimo in cars_by_model
                car_info = cars_by_model.get(best_model)
                if car_info:
                    link = car_info["link"]
                    # Visito la pagina e estraggo dettagli
                    try:
                        page.goto(link, timeout=45_000)
                        page.wait_for_load_state("networkidle")
                        details = parse_car_page(page)
                        # Unisco i dati base di cars.json con quelli di dettaglio
                        selected_details = {
                            "model": best_model,
                            "link": link,
                            "price_eur": car_info["price_eur"],
                            "price_text": car_info["price_text"],
                            **details
                        }
                    except TE:
                        # In caso di timeout, lascio selected_details a None
                        selected_details = None
                else:
                    # Nessuna corrispondenza in cars.json
                    selected_details = None
            else:
                # Nessun veicolo associato al gruppo
                selected_details = None

            # Aggiungo il campo 'selected_car_details'
            gruppo_output["selected_car_details"] = selected_details
            output_groups.append(gruppo_output)

        browser.close()

    # Scrivo in OUTPUT_FILE
    OUTPUT_FILE.write_text(
        json.dumps(output_groups, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"✓ Creato '{OUTPUT_FILE}' con i dettagli delle auto selezionate per ciascun gruppo.")

if __name__ == "__main__":
    SETTINGS = json.load(open("global_params.json", "r"))
    step_5(SETTINGS)
