"""discovercars_playwright.py
Automazione Playwright completa per discovercars.com
----------------------------------------------------
1. Inserisce il luogo di ritiro e seleziona la prima voce proposta.
2. Imposta **solo** le date (niente orari) nei campi hidden + UI.
3. Avvia la ricerca.
4. **(Opzionale)** seleziona un *gruppo di auto* (Small cars, SUVs, ecc.) tramite il
   filtro orizzontale "Car groups" se `car_group` è specificato.
5. Ordina i risultati per **prezzo** (crescente).
6. Clicca "Show more" finché presente per caricare tutte le schede.
7. Estrae **nome** e **link** di ogni veicolo e salva tutto in *cars.json* con
   struttura:

   {
       "total_results": 123,
       "cars": [ {"name": "Fiat Panda", "link": "…"}, … ]
   }

Esecuzione:
    python discovercars_playwright.py

Requisiti:
    pip install playwright
    playwright install
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

# ----------------------------------------------------------------------------
# CONFIGURAZIONE -------------------------------------------------------------
# ----------------------------------------------------------------------------

SETTINGS = {
    "location": "Naples Airport (NAP)",
    "pick_date": "2025-05-29",        # YYYY-MM-DD
    "drop_date": "2025-06-06",        # YYYY-MM-DD
    "car_group": "Small Cars",             # None, "small", "suv", "premium", …
    "headless": False,
    "slow_mo": None,                   # es. 200 (ms) per debug
    "output_file": "cars.json",
}

BASE_URL = "https://www.discovercars.com"

# ----------------------------------------------------------------------------
# FUNZIONI DI SUPPORTO -------------------------------------------------------
# ----------------------------------------------------------------------------

def _ui_date(date_str: str) -> str:
    return datetime.strptime(date_str, "%Y-%m-%d").strftime("%a, %d %b, %Y")


def _inject_dates(page, pick_date: str, drop_date: str):
    """Scrive le date nei campi nascosti + UI e dispatcha un evento *change*."""
    page.evaluate(
        "(d) => {\n"
        "  const set = (hid, ui, val, pretty) => {\n"
        "    const h = document.getElementById(hid);\n"
        "    const u = document.getElementById(ui);\n"
        "    h.value = val;\n"
        "    u.value = pretty;\n"
        "    h.dispatchEvent(new Event('change', { bubbles: true }));\n"
        "  };\n"
        "  set('pick-date', 'pick-date-ui', d.p, d.up);\n"
        "  set('drop-date', 'drop-date-ui', d.d, d.ud);\n"
        "}",
        {
            "p": pick_date,
            "d": drop_date,
            "up": _ui_date(pick_date),
            "ud": _ui_date(drop_date),
        },
    )


def _select_car_group(page, group: str | None):
    """Clicca sul filtro del "Car group" richiesto, se disponibile."""
    if not group:
        return

    # accetta sia value (small, suv…) sia id (car-groups-small) sia etichetta testo
    selectors = [
        f"div.car-top-filter-item[data-value='{group.lower()}']",
        f"div.car-top-filter-item[data-id='{group.lower()}']",
        f"div.car-top-filter-item:has-text('{group}')",
    ]
    filt = None
    for sel in selectors:
        if page.locator(sel).count():
            filt = page.locator(sel).first
            break
    if not filt:
        print(f"[WARN] Gruppo auto '{group}' non trovato — salto il filtro.")
        return

    try:
        filt.scroll_into_view_if_needed()
        filt.click()
        # attende che l'item diventi "selected triggered" (classe usata dal sito)
        page.wait_for_selector(
            sel + ".selected.triggered", timeout=10_000
        )
        page.wait_for_load_state("networkidle")
    except PlaywrightTimeoutError:
        print(f"[WARN] Timeout nel selezionare il gruppo '{group}'.")


def _sort_by_price(page):
    try:
        page.locator("div.dropdown.inline-block > a.dropdown-toggle").click()
        price_item = page.locator("li.sort-by-list[data-type='cheapest']")
        if price_item and not price_item.get_attribute("class").count("active"):
            price_item.click()
        page.wait_for_load_state("networkidle")
    except PlaywrightTimeoutError:
        print("[WARN] Ordinamento per prezzo non applicato.")


def _click_show_more_until_end(page):
    while page.locator("a.show-more-cars:visible").count():
        btn = page.locator("a.show-more-cars:visible").first
        current = page.locator(".car-box").count()
        try:
            btn.scroll_into_view_if_needed()
            btn.click()
            page.wait_for_function(
                "(old) => document.querySelectorAll('.car-box').length > old",
                arg=current,
                timeout=10_000,
            )
            page.wait_for_load_state("networkidle")
        except PlaywrightTimeoutError:
            break


def _scrape_results(page):
    """Raccoglie nome, link e prezzo (float in EUR) di ogni veicolo."""
    page.wait_for_selector(".car-box .car-name a", timeout=20_000)

    # elementi <a> con il nome e l’href
    anchors = page.locator(".car-box .car-name a")
    names  = anchors.all_inner_texts()
    hrefs  = anchors.evaluate_all("els => els.map(e => e.getAttribute('href'))")

    # prezzo principale visualizzato – es: "€177.09"
    prices_text = page.locator(".car-box .price-item-price-main").all_inner_texts()

    cars = []
    for name, href, ptxt in zip(names, hrefs, prices_text):
        if not href:
            continue
        # pulizia prezzo → float
        price_eur = None
        try:
            price_eur = float(ptxt.replace("€", "").replace(",", "").strip())
        except ValueError:
            pass

        cars.append({
            "name": name.strip(),
            "link": urljoin(BASE_URL, href),
            "price_eur": price_eur,   # numerico per ordinamenti / filtri futuri
            "price_text": ptxt.strip()  # stringa originale conservata
        })
    return cars

# ----------------------------------------------------------------------------
# MAIN -----------------------------------------------------------------------
# ----------------------------------------------------------------------------

def run(*, location: str, pick_date: str, drop_date: str, car_group: str | None, headless: bool, slow_mo, output_file: str):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless, slow_mo=slow_mo)
        page = browser.new_page()

        # home
        page.goto(BASE_URL, timeout=45_000)

        # cookie banner
        try:
            page.click("button:has-text('Accept')", timeout=6_000)
        except PlaywrightTimeoutError:
            pass

        # location + suggestion
        page.fill("#pick-up-location", location)
        try:
            page.wait_for_selector(".tt-dataset-locations .tt-suggestion", timeout=8_000)
            page.locator(".tt-dataset-locations .tt-suggestion").first.click()
        except PlaywrightTimeoutError:
            print("[WARN] Nessun suggerimento; uso testo inserito.")

        # dates
        _inject_dates(page, pick_date, drop_date)

        # search
        page.click("#location-submit")
        page.wait_for_load_state("networkidle")

        # car group filter (opzionale)
        _select_car_group(page, car_group)

        # ordina per prezzo
        _sort_by_price(page)

        # carica tutti i risultati
        _click_show_more_until_end(page)

        # scrape
        cars = _scrape_results(page)
        total = len(cars)

        output = {"total_results": total, "cars": cars}
        out_path = Path(output_file).resolve()
        out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"\n[✓] Veicoli trovati: {total} — salvati in {out_path}\n")
        print(json.dumps(output, ensure_ascii=False, indent=2))
        print("\n[i] Chiudi il browser o premi INVIO per terminare…")
        try:
            input()
        except KeyboardInterrupt:
            pass
        finally:
            browser.close()


if __name__ == "__main__":
    run(**SETTINGS)
