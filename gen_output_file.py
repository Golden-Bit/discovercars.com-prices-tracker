#!/usr/bin/env python3
"""
build_comparison_xlsx.py
────────────────────────
Crea un foglio Excel che, per ogni gruppo SIPP, riporta il **prezzo
finale** della migliore offerta selezionata sui diversi periodi.

Regole di calcolo del prezzo finale:

1.  Se `pay_on_arrival` > 0   →  **prezzo = pay_on_arrival − 1 €**
2.  Se `pay_on_arrival` == 0  →  **prezzo = (pay_now × (1 − BROKER_FEE)) − 1 €**

dove `BROKER_FEE` è la commissione del broker (default = 30 % → 0.30).

Il foglio risultante avrà:

* Riga indice = codici SIPP.
* Colonne     = giorni di periodo (cartelle numeriche).
* Celle       = prezzo calcolato (float, 2 decimali) o vuota se
  assente/non calcolabile.
"""

import json
import re
from pathlib import Path
import pandas as pd

# ────────────────────────────────────────────────────────────────────────────
# Parametri configurabili
# ────────────────────────────────────────────────────────────────────────────
BROKER_FEE = 0.30    # 30 %  (imposta a piacere)

# ────────────────────────────────────────────────────────────────────────────
# Utility
# ────────────────────────────────────────────────────────────────────────────
def _slugify(text: str) -> str:
    import unicodedata
    norm = unicodedata.normalize("NFKD", text)
    return re.sub(r"[^\w]+", "_", norm.encode("ascii", "ignore").decode()).strip("_").lower()

# ────────────────────────────────────────────────────────────────────────────
# Funzione principale
# ────────────────────────────────────────────────────────────────────────────
def gen_output_file(settings: dict):
    location  = settings["location"]
    pick_date = settings["pick_date"]

    slug_loc = _slugify(location)
    base_dir = Path("data") / slug_loc

    if not base_dir.exists():
        raise SystemExit(f"Cartella base '{base_dir}' inesistente.")

    # raccoglie cartelle di periodo (nomi numerici)
    period_dirs = sorted(
        (p for p in base_dir.iterdir() if p.is_dir() and p.name.isdigit()),
        key=lambda p: int(p.name)
    )
    if not period_dirs:
        raise SystemExit("Nessuna sottocartella di periodo trovata.")

    data_per_period: dict[int, dict[str, float]] = {}
    all_groups: set[str] = set()

    for pdir in period_dirs:
        days = int(pdir.name)
        json_path = pdir / pick_date / "group_selected_details.json"
        if not json_path.exists():
            print(f"[WARN] Mancante: {json_path}  → periodo {days} ignorato.")
            continue

        groups = json.loads(json_path.read_text(encoding="utf-8"))
        price_map: dict[str, float] = {}

        for g in groups:
            sipp   = g.get("sipp_code", "")
            det    = g.get("selected_car_details")
            if not (sipp and det):
                continue

            pay_now        = det.get("pay_now")
            pay_on_arrival = det.get("pay_on_arrival")

            price: float | None = None
            if isinstance(pay_on_arrival, (int, float)) and pay_on_arrival > 0:
                price = pay_on_arrival
            elif isinstance(pay_now, (int, float)):
                price = pay_now * (1.0 - BROKER_FEE)

            if price is not None:
                price = round(price - 1.0, 2)   # −1 €
                if price < 0:
                    price = 0.0
                price_map[sipp] = price
                all_groups.add(sipp)

        if price_map:
            data_per_period[days] = price_map

    if not data_per_period:
        raise SystemExit("Nessun dato valido per alcun periodo.")

    # costruzione DataFrame
    periods = sorted(data_per_period.keys())
    groups  = sorted(all_groups)
    df = pd.DataFrame(index=groups, columns=periods, dtype=float)

    for days, pmap in data_per_period.items():
        for sipp in groups:
            df.at[sipp, days] = pmap.get(sipp, "")

    df.index.name   = "SIPP_Code"
    df.columns.name = "Period_Days"

    outfile = f"comparison_{slug_loc}_{pick_date}.xlsx"
    df.to_excel(outfile, engine="openpyxl")
    print(f"✓ Excel scritto: '{outfile}'")

# ────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    SETTINGS = json.load(open("global_params.json", "r"))
    gen_output_file(SETTINGS)
