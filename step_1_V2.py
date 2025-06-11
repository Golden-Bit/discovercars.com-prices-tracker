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
    Seleziona il layout corretto:
    - Se esistono .SearchCar-CarNameLink → nuovo layout (searchVersion=2)
    - Altrimenti fallback al layout classico (searchVersion=1)
    Estrae nome, link e prezzo.
    """
    cars = []

    # Nuovo layout (lazy-loaded): aspetta almeno un wrapper
    if page.locator(".SearchCar-Wrapper").count() > 0:
        wrappers = page.locator(".SearchCar-Wrapper").all()
        for wrapper in wrappers:
            name_elem = wrapper.locator(".SearchCar-CarNameLink").first
            name = name_elem.inner_text().strip() if name_elem.count() else ""
            href = name_elem.get_attribute("href") if name_elem.count() else None
            price_elem = wrapper.locator(".SearchCar-Price").first
            price_text = price_elem.inner_text().strip() if price_elem.count() else ""
            try:
                price_eur = float(price_text.replace("€", "").replace(",", "").strip())
            except ValueError:
                price_eur = None
            if href:
                cars.append({
                    "name": name,
                    "link": urljoin(BASE_URL, href),
                    "price_eur": price_eur,
                    "price_text": price_text
                })
        return cars

    # Fallback layout classico
    anchors = page.locator(".car-box .car-name a")
    names = anchors.all_inner_texts()
    anchor_elements = anchors.all()
    hrefs = [anchor.get_attribute("href") for anchor in anchor_elements]
    prices_text = page.locator(".car-box .price-item-price-main").all_inner_texts()
    for name, href, ptxt in zip(names, hrefs, prices_text):
        if not href:
            continue
        try:
            price_eur = float(ptxt.replace("€", "").replace(",", "").strip())
        except ValueError:
            price_eur = None
        cars.append({
            "name": name.strip(),
            "link": urljoin(BASE_URL, href),
            "price_eur": price_eur,
            "price_text": ptxt.strip()
        })
    return cars

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
    fmt = "%Y-%m-%d"
    dt_pick = datetime.strptime(pick_date, fmt)
    dt_drop = datetime.strptime(drop_date, fmt)
    period_days = (dt_drop - dt_pick).days

    slug_loc = _slugify(location)
    work_dir = Path("data") / slug_loc / str(period_days) / pick_date
    work_dir = work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    out_path = work_dir / output_file

    max_attempts = 5
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

                # Controllo e modifica del parametro searchVersion
                current_url = page.url
                if "searchVersion=1" in current_url or "searchVersion=0" in current_url:
                    new_url = current_url.replace("searchVersion=0", "searchVersion=2")
                    new_url = new_url.replace("searchVersion=1", "searchVersion=2")
                    print(f"[INFO] Rilevato searchVersion!=2, ricarico con searchVersion=2: {new_url}")
                    page.goto(new_url, timeout=45_000)
                    page.wait_for_load_state("networkidle")
                    # Aspetto esplicitamente che il nuovo layout abbia almeno una card
                    try:
                        page.wait_for_selector(".SearchCar-Wrapper", timeout=15000)
                    except PlaywrightTimeoutError:
                        print("[WARN] Timeout nell'attesa delle card SearchCar-Wrapper")
                    time.sleep(2)

                _sort_by_price(page)
                time.sleep(2)

                # Se siamo nella versione 2, facciamo scrolling per caricare tutti i risultati
                if page.locator(".SearchCar-Wrapper").count() > 0:
                    previous_count = 0
                    while True:
                        # Scroll fino in fondo
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        time.sleep(1)
                        # Attendo un po' che si carichino eventuali nuovi elementi
                        page.wait_for_load_state("networkidle")
                        time.sleep(1)
                        current_count = page.locator(".SearchCar-Wrapper").count()
                        if current_count == previous_count:
                            break
                        previous_count = current_count

                cars = _scrape_results(page)
                if cars:
                    print(f"[INFO] Trovati {len(cars)} veicoli.")
                    break
                else:
                    print("[WARN] Nessun veicolo trovato, riprovo...")
        except Exception as e:
            print(f"[ERROR] Errore durante il tentativo {attempt}: {e}")
        finally:
            try:
                browser.close()
            except:
                pass
        time.sleep(2)

    if cars:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"total_results": len(cars), "cars": cars}, f, ensure_ascii=False, indent=2)
        print(f"\n[✓] Veicoli trovati: {len(cars)} — salvati in {out_path}\n")
    else:
        print("[ERROR] Nessun veicolo trovato dopo 5 tentativi.")

if __name__ == "__main__":
    run(**SETTINGS)
