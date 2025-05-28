#!/usr/bin/env python3
"""
verify_groups.py
────────────────
Confronta:

1. Il file `car_names.json` (lista di nomi) che vive dentro una
   *cartella di lavoro* WORK_DIR.

2. Il file dei gruppi SIPP (`gruppi_sipp.json`) che rimane nella
   *root di progetto* accanto a questo script.

La variabile WORK_DIR può essere impostata qui sotto **oppure** passata
come PRIMO argomento da riga di comando:

    python verify_groups.py naples_airport_nap_2025-05-29
"""

from pathlib import Path
from textwrap import indent
import json
import sys

# ---------------------------------------------------------------------------
# PERCORSI DI INPUT ----------------------------------------------------------
# ---------------------------------------------------------------------------

# Cartella di lavoro: dove il flusso scraping ha generato car_names.json
WORK_DIR = Path("data/naples_airport_nap_2025-05-29").resolve()
if len(sys.argv) > 1:                               # override opzionale
    WORK_DIR = Path(sys.argv[1]).expanduser().resolve()

NAMES_FILE = WORK_DIR / "car_names.json"            # lista modelli
GROUPS_FILE = Path(__file__).with_name("gruppi_sipp.json")  # sempre in root

# ---------------------------------------------------------------------------
# FUNZIONI DI CARICO DATI ----------------------------------------------------
# ---------------------------------------------------------------------------


def load_names_from_list(path: Path) -> set[str]:
    """Carica JSON array di stringhe → set ripulito (spazi, vuoti)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} non contiene un array JSON.")
    return {str(x).strip() for x in data if str(x).strip()}


def load_names_from_groups(path: Path) -> set[str]:
    """Carica JSON gruppi e accumula tutti i nomi in vehicles[]."""
    groups = json.loads(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for g in groups:
        names.update({str(v).strip() for v in g.get("vehicles", [])})
    return names


# ---------------------------------------------------------------------------
# MAIN -----------------------------------------------------------------------
# ---------------------------------------------------------------------------


def main():
    if not NAMES_FILE.exists():
        sys.exit(f"Errore: '{NAMES_FILE}' non trovato – controlla WORK_DIR.")
    if not GROUPS_FILE.exists():
        sys.exit(f"Errore: '{GROUPS_FILE}' non trovato nella root di progetto.")

    list_names = load_names_from_list(NAMES_FILE)
    group_names = load_names_from_groups(GROUPS_FILE)

    missing_in_groups = list_names - group_names
    extra_in_groups = group_names - list_names

    print("─ Statistiche ─")
    print(f"Modelli unici nella lista    : {len(list_names)}")
    print(f"Modelli unici nei gruppi     : {len(group_names)}\n")

    if missing_in_groups:
        print(f"⚠️  Presenti NELLA LISTA ma ASSENTI nei gruppi ({len(missing_in_groups)}):")
        print(indent("\n".join(sorted(missing_in_groups)), "  "))
    else:
        print("✅ Nessun modello manca nei gruppi.")

    print()

    if extra_in_groups:
        print(f"⚠️  Presenti NEI GRUPPI ma ASSENTI nella lista ({len(extra_in_groups)}):")
        print(indent("\n".join(sorted(extra_in_groups)), "  "))
    else:
        print("✅ Nessun modello extra nei gruppi.")


if __name__ == "__main__":
    main()
