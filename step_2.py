#!/usr/bin/env python3
"""
extract_car_names.py
────────────────────
Legge il file `cars.json` creato da `discovercars_playwright.py`
dentro una *cartella di lavoro* (WORK_DIR) e genera, nella stessa
cartella, `car_names.json` con **l’elenco unico** dei modelli trovati.

USO
----
• Imposta la variabile WORK_DIR qui sotto **oppure** passala come
  primo argomento da riga di comando:

    python extract_car_names.py naples_airport_nap_2025-05-29

• Il programma crea/aggiorna `car_names.json` nella cartella indicata.
"""
from datetime import datetime
from pathlib import Path
import json
import sys

from step_1 import _slugify

# ---------------------------------------------------------------------------
# MAIN -----------------------------------------------------------------------
# ---------------------------------------------------------------------------

def step_2(settings: dict):
    location  = settings["location"]
    pick_date = settings["pick_date"]
    drop_date = settings["drop_date"]

    # ――― Calcolo del periodo in giorni ―――
    fmt = "%Y-%m-%d"
    dt_pick = datetime.strptime(pick_date, fmt)
    dt_drop = datetime.strptime(drop_date, fmt)
    period_days = (dt_drop - dt_pick).days

    # ――― Nuova struttura cartelle:
    # data/<slugify(location)>/<period_days>/<pick_date>/
    slug_loc = _slugify(location)
    work_dir = Path("data") / slug_loc / str(period_days) / pick_date
    work_dir = work_dir.resolve()

    src_file  = work_dir / "cars.json"
    dest_file = work_dir / "car_names.json"

    if not src_file.exists():
        sys.exit(f"Errore: '{src_file}' non trovato. Controlla WORK_DIR.")

    # ――― Carica il JSON sorgente ―――
    data = json.loads(src_file.read_text(encoding="utf-8"))

    # ――― Estrae nomi unici (case-sensitive) ―――
    names = sorted({car.get("name", "").strip() for car in data.get("cars", []) if car.get("name")})

    # ――― Scrive il nuovo file ―――
    work_dir.mkdir(parents=True, exist_ok=True)
    dest_file.write_text(json.dumps(names, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✓ Salvati {len(names)} nomi in {dest_file}")


if __name__ == "__main__":
    SETTINGS = json.load(open("global_params.json", "r"))
    step_2(SETTINGS)
