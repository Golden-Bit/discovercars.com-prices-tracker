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

from pathlib import Path
import json
import sys

# ---------------------------------------------------------------------------
# CARTELLA DI LAVORO ---------------------------------------------------------
# ---------------------------------------------------------------------------

# Default (puoi sovrascrivere via CLI)
WORK_DIR = Path("data/naples_airport_nap_2025-05-29").resolve()
if len(sys.argv) > 1:                           # override opzionale
    WORK_DIR = Path(sys.argv[1]).expanduser().resolve()

# Percorsi file
SRC_FILE = WORK_DIR / "cars.json"
DEST_FILE = WORK_DIR / "car_names.json"

# ---------------------------------------------------------------------------
# MAIN -----------------------------------------------------------------------
# ---------------------------------------------------------------------------


def main():
    if not SRC_FILE.exists():
        sys.exit(f"Errore: '{SRC_FILE}' non trovato. Controlla WORK_DIR.")

    # ――― Carica il JSON sorgente ―――
    data = json.loads(SRC_FILE.read_text(encoding="utf-8"))

    # ――― Estrae nomi unici (case-sensitive) ―――
    names = sorted({car.get("name", "").strip() for car in data.get("cars", []) if car.get("name")})

    # ――― Scrive il nuovo file ―――
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    DEST_FILE.write_text(json.dumps(names, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✓ Salvati {len(names)} nomi in {DEST_FILE}")


if __name__ == "__main__":
    main()
