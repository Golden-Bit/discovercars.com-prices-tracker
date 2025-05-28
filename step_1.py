#!/usr/bin/env python3
"""
discovercars_playwright.py
──────────────────────────
Automazione Playwright per discovercars.com

1. Inserisce il luogo di ritiro e seleziona la prima voce proposta.
2. Imposta **solo le date** (niente orari) nei campi hidden + UI.
3. Avvia la ricerca.
4. **(Opzionale)** seleziona un *gruppo di auto* (Small cars, SUVs, ecc.)
   tramite il filtro orizzontale “Car groups” se `car_group` è specificato.
5. Ordina i risultati per **prezzo** (crescente).
6. Clicca “Show more” finché presente per caricare tutte le schede.
7. Estrae **name**, **link**, **price_eur**, **price_text** di ogni veicolo e salva
   il tutto in *cars.json* dentro una cartella dedicata:

   <slug_location>_<pick_date>/
      └── cars.json
        {
          "total_results": 123,
          "cars": [
            {
              "name": "Fiat Panda",
              "link": "https://…",
              "price_eur": 177.09,
              "price_text": "€177.09"
            },
            …
          ]
        }

Esecuzione:
    python discovercars_playwright.py

Prerequisiti:
    pip install playwright
    playwright install
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

# ----------------------------------------------------------------------------
# CONFIGURAZIONE -------------------------------------------------------------
# ----------------------------------------------------------------------------

SETTINGS = {
    "location": "Naples Airport (NAP)",   # luogo/slug verrà usato per la dir
    "pick_date": "2025-05-29",            # YYYY-MM-DD
    "drop_date": "2025-06-06",            # YYYY-MM-DD
    "car_group": "Small Cars",            # None, "small", "suv", "premium", …
    "headless": False,
    "slow_mo": None,                      # es. 200 ms per debug; None = max velocità
    "output_file": "cars.json",           # nome file dentro la cartella
}

BASE_URL = "https://www.discovercars.com"

# ----------------------------------------------------------------------------
# UTILITY: cartella di output ------------------------------------------------
# ----------------------------------------------------------------------------


def _slugify(text: str) -> str:
    """
    Converte la stringa in slug filesystem-safe:
    - rimuove accentate
    - sostituisce non alfanumerico con '_'
    - converte in minuscolo
    """
    import unicodedata

    norm = unicodedata.normalize("NFKD", text)
    ascii_txt = norm.encode("ascii", "ignore").decode()
    slug = re.sub(r"[^\w]+", "_", ascii_txt).strip("_").lower()
    return slug


# ----------------------------------------------------------------------------
# FUNZIONI DI SUPPORTO -------------------------------------------------------
# ----------------------------------------------------------------------------


def _ui_date(date_str: str) -> str:
    """YYYY-MM-DD → 'Thu, 29 May, 2025' per i campi UI."""
    return datetime.strptime(date_str, "%Y-%m-%d").strftime("%a, %d %b, %Y")


def _inject_dates(page, pick_date: str, drop_date: str):
    """Scrive date nei campi hidden + UI e dispatcha un evento change."""
    page.evaluate(
        "(d) => {                                           \n"
        "  const set = (hid, ui, val, pretty) => {          \n"
        "    const h = document.getElementById(hid);        \n"
        "    const u = document.getElementById(ui);         \n"
        "    h.value = val;                                 \n"
        "    u.value = pretty;                              \n"
        "    h.dispatchEvent(new Event('change', { bubbles:true }));\n"
        "  };                                               \n"
        "  set('pick-date', 'pick-date-ui', d.p, d.up);     \n"
        "  set('drop-date', 'drop-date-ui', d.d, d.ud);     \n"
        "}",
        {
            "p": pick_date,
            "d": drop_date,
            "up": _ui_date(pick_date),
            "ud": _ui_date(drop_date),
        },
    )


def _select_car_group(page, group: str | None):
    """Clicca sul filtro 'Car group' se presente."""
    if not group:
        return

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
        print(f"[WARN] Gruppo auto “{group}” non trovato — skip.")
        return

    try:
        filt.scroll_into_view_if_needed()
        filt.click()
        page.wait_for_selector(sel + ".selected.triggered", timeout=10_000)
        page.wait_for_load_state("networkidle")
    except PlaywrightTimeoutError:
        print(f"[WARN] Timeout nel selezionare il gruppo “{group}”.")
        return


def _sort_by_price(page):
    try:
        page.locator("div.dropdown.inline-block > a.dropdown-toggle").click()
        price_item = page.locator("li.sort-by-list[data-type='cheapest']")
        if price_item and "active" not in (price_item.get_attribute("class") or ""):
            price_item.click()
        page.wait_for_load_state("networkidle")
    except PlaywrightTimeoutError:
        print("[WARN] Ordinamento per prezzo non applicato.")


def _click_show_more_until_end(page):
    """Carica tutte le card cliccando 'Show more' finché compare."""
    while page.locator("a.show-more-cars:visible").count():
        btn = page.locator("a.show-more-cars:visible").first
        current = page.locator(".car-box").count()
        try:
            btn.scroll_into_view_if_needed()
            btn.click()
            page.wait_for_function(
                "(old) => document.querySelectorAll('.car-box').length > old",
                arg=current,
                timeout=30_000,
            )
            page.wait_for_load_state("networkidle")
        except PlaywrightTimeoutError:
            break


def _scrape_results(page):
    """Raccoglie nome, link, prezzo di ogni veicolo nei risultati."""
    anchors = page.locator(".car-box .car-name a")
    names = anchors.all_inner_texts()
    hrefs = anchors.evaluate_all("els => els.map(e => els.map(e=>e.getAttribute('href')))")[0] \
        if anchors.count() else []
    prices_text = page.locator(".car-box .price-item-price-main").all_inner_texts()

    cars = []
    for name, href, ptxt in zip(names, hrefs, prices_text):
        if not href:
            continue
        try:
            price_eur = float(ptxt.replace("€", "").replace(",", "").strip())
        except ValueError:
            price_eur = None

        cars.append(
            {
                "name": name.strip(),
                "link": urljoin(BASE_URL, href),
                "price_eur": price_eur,
                "price_text": ptxt.strip(),
            }
        )
    return cars


# ----------------------------------------------------------------------------
# MAIN -----------------------------------------------------------------------
# ----------------------------------------------------------------------------


def run(
    *,
    location: str,
    pick_date: str,
    drop_date: str,
    car_group: str | None,
    headless: bool,
    slow_mo,
    output_file: str,
):
    # ――― cartella dedicata per questa ricerca ―――
    work_dir = Path(f"data/{_slugify(location)}_{pick_date}").resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    out_path = work_dir / output_file

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless, slow_mo=slow_mo)
        page = browser.new_page()

        # 1. Home
        page.goto(BASE_URL, timeout=45_000)

        # 2. Cookie banner
        try:
            page.click("button:has-text('Accept')", timeout=6_000)
        except PlaywrightTimeoutError:
            pass

        # 3. Location + suggestion
        page.fill("#pick-up-location", location)
        try:
            page.wait_for_selector(".tt-dataset-locations .tt-suggestion", timeout=8_000)
            page.locator(".tt-dataset-locations .tt-suggestion").first.click()
        except PlaywrightTimeoutError:
            print("[WARN] Nessun suggerimento; continuo con il testo inserito.")

        # 4. Date
        _inject_dates(page, pick_date, drop_date)

        # 5. Search
        page.click("#location-submit")
        page.wait_for_load_state("networkidle")

        # 6. Car group filter (opzionale)
        _select_car_group(page, car_group)

        time.sleep(2)

        # 7. Ordina per prezzo
        _sort_by_price(page)

        time.sleep(2)

        # 8. Carica tutti i risultati (decommenta se necessario)
        # _click_show_more_until_end(page)

        # 9. Scraping
        cars = _scrape_results(page)
        total = len(cars)

        # 10. Salvataggio JSON
        (work_dir / output_file).write_text(
            json.dumps({"total_results": total, "cars": cars}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print(f"\n[✓] Veicoli trovati: {total} — salvati in {out_path}\n")
        print(json.dumps({"total_results": total, "cars": cars}, ensure_ascii=False, indent=2))
        print("\n[i] Chiudi il browser o premi INVIO per terminare…")
        try:
            input()
        except KeyboardInterrupt:
            pass
        finally:
            browser.close()


if __name__ == "__main__":
    run(**SETTINGS)
