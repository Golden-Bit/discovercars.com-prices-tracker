#!/usr/bin/env python3
"""
step_1_async.py  –  scraping lista auto (Playwright asincrono)
───────────────────────────────────────────────────────────────
Chiamata tipica da Streamlit:

    await step_1_async(**settings)

Oppure da CLI:

    python step_1_async.py
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

from playwright.async_api import async_playwright, TimeoutError

BASE_URL = "https://www.discovercars.com"


# ────────────────────────────────────────────────────────────────────────────
# UTILITIES
# ────────────────────────────────────────────────────────────────────────────
def _slugify(text: str) -> str:
    import unicodedata
    norm = unicodedata.normalize("NFKD", text)
    return re.sub(r"[^\w]+", "_", norm.encode("ascii", "ignore").decode()).strip("_").lower()


def _ui_date(date_str: str) -> str:
    return datetime.strptime(date_str, "%Y-%m-%d").strftime("%a, %d %b, %Y")


async def _inject_dates(page, pick: str, drop: str):
    await page.evaluate(
        """(d) => {
              const set = (hid, ui, v, pretty) => {
                 const h = document.getElementById(hid);
                 const u = document.getElementById(ui);
                 h.value = v;
                 u.value = pretty;
                 h.dispatchEvent(new Event('change', { bubbles:true }));
              };
              set('pick-date',  'pick-date-ui',  d.p, d.up);
              set('drop-date',  'drop-date-ui',  d.d, d.ud);
        }""",
        {
            "p": pick,
            "d": drop,
            "up": _ui_date(pick),
            "ud": _ui_date(drop),
        },
    )


async def _sort_by_price(page):
    try:
        await page.locator("div.dropdown.inline-block > a.dropdown-toggle").click()
        price_item = page.locator("li.sort-by-list[data-type='cheapest']")
        if price_item:
            cls = await price_item.get_attribute("class") or ""
            if "active" not in cls:
                await price_item.click()
        await page.wait_for_load_state("networkidle")
    except TimeoutError:
        print("[WARN] Ordinamento per prezzo non applicato.")


async def _scrape_results(page):
    anchors = page.locator(".car-box .car-name a")
    names   = await anchors.all_inner_texts()
    hrefs   = [await a.get_attribute("href") for a in await anchors.all()]
    prices  = await page.locator(".car-box .price-item-price-main").all_inner_texts()

    cars = []
    for name, href, ptxt in zip(names, hrefs, prices):
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
            "price_text": ptxt.strip(),
        })
    return cars


# ────────────────────────────────────────────────────────────────────────────
#  MAIN ASYNC STEP
# ────────────────────────────────────────────────────────────────────────────
async def step_1_async(
    *,
    location: str,
    pick_date: str,
    drop_date: str,
    car_group: str | None = None,
    headless: bool = True,
    slow_mo: int | None = None,
    output_file: str = "cars.json",
):
    fmt = "%Y-%m-%d"
    period_days = (datetime.strptime(drop_date, fmt) -
                   datetime.strptime(pick_date, fmt)).days

    work_dir = Path("data") / _slugify(location) / str(period_days) / pick_date
    work_dir.mkdir(parents=True, exist_ok=True)
    out_path = work_dir / output_file

    max_attempts, attempt = 5, 0
    cars: list[dict] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless, slow_mo=slow_mo)
        while attempt < max_attempts:
            attempt += 1
            print(f"[INFO] Tentativo {attempt}/{max_attempts}")
            page = await browser.new_page()
            try:
                await page.goto(BASE_URL, timeout=45_000)
                # cookie banner
                try:
                    await page.click("button:has-text('Accept')", timeout=6_000)
                except TimeoutError:
                    pass

                await page.fill("#pick-up-location", location)
                try:
                    await page.wait_for_selector(".tt-dataset-locations .tt-suggestion", timeout=8_000)
                    await page.locator(".tt-dataset-locations .tt-suggestion").first.click()
                except TimeoutError:
                    print("[WARN] Nessun suggerimento; continuo con il testo inserito.")

                await _inject_dates(page, pick_date, drop_date)
                await page.click("#location-submit")
                await page.wait_for_load_state("networkidle")

                # forza searchVersion=0
                cur_url = page.url
                if ("searchVersion=1" in cur_url) or ("searchVersion=2" in cur_url):
                    new_url = cur_url.replace("searchVersion=1", "searchVersion=0") \
                                     .replace("searchVersion=2", "searchVersion=0")
                    print("[INFO] Ricarico con searchVersion=0")
                    await page.goto(new_url)
                    await page.wait_for_load_state("networkidle")

                # gestisce eventuale "no result" con reload
                for _ in range(5):
                    if await page.locator("#load-data-no-result").is_visible():
                        print("[WARN] Nessun risultato, ricarico…")
                        await asyncio.sleep(5)
                        await page.reload()
                        await page.wait_for_load_state("networkidle")
                    else:
                        break
                else:
                    await page.close()
                    continue  # passo al tentativo successivo

                await _sort_by_price(page)
                cars = await _scrape_results(page)
                if cars:
                    print(f"[INFO] Trovati {len(cars)} veicoli.")
                    await page.close()
                    break
                await page.close()
            except Exception as e:
                print(f"[ERROR] {e}")
                await page.close()

        await browser.close()

    if cars:
        out_path.write_text(json.dumps({"total_results": len(cars), "cars": cars},
                                       ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✓ Veicoli salvati in {out_path}")
    else:
        print("✗ Nessun veicolo trovato.")


# ────────────────────────────────────────────────────────────────────────────
#  EXECUTION ENTRY (CLI)
# ────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    SETTINGS = json.load(open("global_params.json", "r"))
    asyncio.run(step_1_async(**SETTINGS))
