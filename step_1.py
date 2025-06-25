# 👈 aggiungi queste righe il più in alto possibile,
#     PRIMA di importare playwright o streamlit!
#import sys, asyncio

#if sys.platform.startswith("win"):
#    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

SETTINGS = json.load(open("global_params.json", "r"))

BASE_URL = "https://www.discovercars.com"


def _slugify(text: str) -> str:
    import unicodedata
    norm = unicodedata.normalize("NFKD", text)
    ascii_txt = norm.encode("ascii", "ignore").decode()
    slug = re.sub(r"[^\w]+", "_", ascii_txt).strip("_").lower()
    return slug


def _ui_date(date_str: str) -> str:
    return datetime.strptime(date_str, "%Y-%m-%d").strftime("%a, %d %b, %Y")


def _inject_dates(page, pick_date: str, drop_date: str):
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


def _sort_by_price(page):
    try:
        page.locator("div.dropdown.inline-block > a.dropdown-toggle").click()
        price_item = page.locator("li.sort-by-list[data-type='cheapest']")
        if price_item and "active" not in (price_item.get_attribute("class") or ""):
            price_item.click()
        page.wait_for_load_state("networkidle")
    except PlaywrightTimeoutError:
        print("[WARN] Ordinamento per prezzo non applicato.")


def _scrape_results(page):
    """
    Estrae da ciascuna card (.car-box):

        • supplier  – nome del noleggiatore (es. "Ciao Rent Car")
        • name      – modello dell’auto (es. "Fiat Panda")
        • link      – URL dell’offerta
        • price_eur – prezzo in float (solo cifra)
        • price_text– prezzo formattato (stringa originale)

    Restituisce: list[dict]
    """
    # ─────────────────────────────────────────────────────────────
    # 1. Modello, link e prezzo (logica invariata)
    # ─────────────────────────────────────────────────────────────
    anchors        = page.locator(".car-box .car-name a")
    names          = anchors.all_inner_texts()
    anchor_elems   = anchors.all()
    hrefs          = [a.get_attribute("href") for a in anchor_elems]
    prices_text    = page.locator(".car-box .price-item-price-main").all_inner_texts()

    # ─────────────────────────────────────────────────────────────
    # 2. NUOVO: nome fornitore (logo -> attributo ALT)
    # ─────────────────────────────────────────────────────────────
    supplier_imgs  = page.locator(".car-box .car-box-supplier-wrapper img[alt]")
    suppliers      = [img.get_attribute("alt") for img in supplier_imgs.all()]

    # ─────────────────────────────────────────────────────────────
    # 3. Costruzione lista finale
    # ─────────────────────────────────────────────────────────────
    cars = []
    for name, href, ptxt, supplier in zip(names, hrefs, prices_text, suppliers):
        if not href:
            continue
        try:
            price_eur = float(ptxt.replace("€", "").replace(",", "").strip())
        except ValueError:
            price_eur = None

        cars.append({
            "supplier": (supplier or "").strip(),
            "name":     name.strip(),
            "link":     urljoin(BASE_URL, href),
            "price_eur": price_eur,
            "price_text": ptxt.strip(),
        })

    return cars



def step_1(
    *,
    location: str,
    pick_date: str,
    drop_date: str,
    car_group: str | None,
    headless: bool,
    slow_mo,
    output_file: str,
):
    # ――― Calcolo del periodo in giorni ―――
    fmt = "%Y-%m-%d"
    dt_pick = datetime.strptime(pick_date, fmt)
    dt_drop = datetime.strptime(drop_date, fmt)
    period_days = (dt_drop - dt_pick).days

    # ――― Nuova struttura cartelle:
    slug_loc = _slugify(location)
    work_dir = Path("data") / slug_loc / str(period_days) / pick_date
    work_dir = work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    out_path = work_dir / output_file

    max_attempts = 20
    attempt = 0
    cars = []
    while attempt < max_attempts:
        attempt += 1
        print(f"[INFO] Tentativo {attempt} di {max_attempts}")
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=headless, slow_mo=slow_mo)
                page = browser.new_page()
                page.goto(BASE_URL, timeout=45_000)

                # Provo a chiudere il banner dei cookie
                try:
                    page.click("button:has-text('Accept')", timeout=6_000)
                except PlaywrightTimeoutError:
                    pass

                page.fill("#pick-up-location", location)
                try:
                    page.wait_for_selector(".tt-dataset-locations .tt-suggestion", timeout=8_000)
                    page.locator(".tt-dataset-locations .tt-suggestion").first.click()
                except PlaywrightTimeoutError:
                    print("[WARN] Nessun suggerimento; continuo con il testo inserito.")
                _inject_dates(page, pick_date, drop_date)
                page.click("#location-submit")
                page.wait_for_load_state("networkidle")
                time.sleep(2)

                # ――― PRIMO: Controllo e modifica del parametro searchVersion ―――
                current_url = page.url
                if "searchVersion=1" in current_url or "searchVersion=2" in current_url:
                    new_url = current_url.replace("searchVersion=1", "searchVersion=0")
                    new_url = new_url.replace("searchVersion=2", "searchVersion=0")
                    print(f"[INFO] Rilevato searchVersion!=0, ricarico con searchVersion=0: {new_url}")
                    page.evaluate(f"window.location.href = '{new_url}';")
                    page.wait_for_load_state("networkidle")
                    time.sleep(2)

                # ――― POI: Controllo “nessun risultato” e reload se compare ―――
                no_result_selector = "#load-data-no-result"
                for nores_attempt in range(5):
                    if page.locator(no_result_selector).is_visible():
                        print(
                            f"[WARN] Nessun risultato trovato (tentativo reload {nores_attempt+1}/5). "
                            "Attendo 5 secondi e ricarico."
                        )
                        time.sleep(5)
                        page.reload()
                        page.wait_for_load_state("networkidle")
                        time.sleep(2)
                    else:
                        break
                else:
                    # Dopo 5 reload ancora no result: esco da tentativo corrente
                    print("[ERROR] Dopo 5 reload continui 'nessun risultato'. Interrompo questo tentativo.")
                    browser.close()
                    continue  # passa al prossimo attempt esterno

                _sort_by_price(page)
                time.sleep(2)
                cars = _scrape_results(page)
                if cars:
                    print(f"[INFO] Trovati {len(cars)} veicoli.")
                    browser.close()
                    break
                else:
                    print("[WARN] Nessun veicolo trovato nonostante risultati attesi, riprovo...")
                    browser.close()
        except Exception as e:
            print(f"[ERROR] Errore durante il tentativo {attempt}: {e}")
        time.sleep(2)

    if cars:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"total_results": len(cars), "cars": cars}, f, ensure_ascii=False, indent=2)
        print(f"\n[✓] Veicoli trovati: {len(cars)} — salvati in {out_path}\n")
    else:
        print(f"[ERROR] Nessun veicolo trovato dopo {max_attempts} tentativi.")


if __name__ == "__main__":
    step_1(**SETTINGS)
