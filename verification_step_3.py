#!/usr/bin/env python3
"""
verify_groups.py   ·  versione compatibile con lo SCHEMA 2 (model + score)
──────────────────────────────────────────────────────────────────────────
Confronta:

1.  `car_names.json`   – array di stringhe con i modelli (nel WORK_DIR)
2.  `gruppi_sipp.json` – array di gruppi con

        "vehicles": [
            { "model": "Fiat 500", "score": 1.0 },
            …
        ]

La variabile WORK_DIR può essere impostata qui sotto **oppure**
passata come PRIMO argomento:

    python verify_groups.py data/naples_airport_nap_2025-05-29
"""

from pathlib import Path
from textwrap import indent
import json
import sys

SETTINGS = json.load(open("global_params.json", "r"))

# ───────────────────────────────────────────────────────────────────────────
# PERCORSI
# ───────────────────────────────────────────────────────────────────────────
WORK_DIR = Path(f"data/{_slugify(SETTINGS['location'])}_{SETTINGS['pick_date']}").resolve()

if len(sys.argv) > 1:          # override facoltativo
    WORK_DIR = Path(sys.argv[1]).expanduser().resolve()

NAMES_FILE  = WORK_DIR / "car_names.json"
GROUPS_FILE = Path(__file__).with_name("gruppi_sipp.json")

# ───────────────────────────────────────────────────────────────────────────
# FUNZIONI
# ───────────────────────────────────────────────────────────────────────────
def load_names_list(path: Path) -> set[str]:
    """Legge un JSON array di stringhe e restituisce l’insieme ripulito."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} non contiene un array JSON.")
    return {str(x).strip() for x in data if str(x).strip()}


def load_names_from_groups(path: Path) -> set[str]:
    """
    Estrae tutti i nomi dalle chiavi 'vehicles'. Ogni item può essere:
      • stringa semplice  (vecchio schema)
      • dict {"model": "...", "score": ...} (nuovo schema)
    """
    groups = json.loads(path.read_text(encoding="utf-8"))
    names: set[str] = set()

    for g in groups:
        for v in g.get("vehicles", []):
            if isinstance(v, str):
                names.add(v.strip())
            elif isinstance(v, dict) and v.get("model"):
                names.add(str(v["model"]).strip())
    return names


def pretty_print_set(title: str, items: set[str]):
    print(f"{title} ({len(items)}):")
    print(indent("\n".join(sorted(items)), "  "))


# ───────────────────────────────────────────────────────────────────────────
# MAIN
# ───────────────────────────────────────────────────────────────────────────
def main():
    if not NAMES_FILE.exists():
        sys.exit(f"❌  '{NAMES_FILE}' non trovato – controlla WORK_DIR.")
    if not GROUPS_FILE.exists():
        sys.exit(f"❌  '{GROUPS_FILE}' non trovato nella root del progetto.")

    list_names  = load_names_list(NAMES_FILE)
    group_names = load_names_from_groups(GROUPS_FILE)

    missing = list_names  - group_names   # in lista ma non nei gruppi
    extra   = group_names - list_names    # nei gruppi ma non nella lista

    print("─ Verifica completata ─")
    print(f"Modelli unici nella lista : {len(list_names)}")
    print(f"Modelli unici nei gruppi  : {len(group_names)}\n")

    if missing:
        pretty_print_set("⚠️  NELLA LISTA ma NON nei gruppi", missing)
    else:
        print("✅ Tutti i modelli della lista sono mappati in almeno un gruppo.\n")

    if extra:
        pretty_print_set("⚠️  NEI GRUPPI ma NON nella lista", extra)
    else:
        print("✅ Nessun modello extra presente nei gruppi.\n")


if __name__ == "__main__":
    main()
