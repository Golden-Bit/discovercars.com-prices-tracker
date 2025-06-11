#!/usr/bin/env python3
"""
multi_period_cli.py
────────────────────
Esegue l’intero workflow DiscoverCars su più “periodi” (durata noleggio
in giorni) forniti dall’utente.

USO
----
    python multi_period_cli.py \
        --location "Naples Airport (NAP)" \
        --pick-date 2025-06-10 \
        --periods 1 2 3 7 \
        [--global-json path/to/global_params.json]

Opzioni
-------
--location/-l        Località (stringa come appare su DiscoverCars)
--pick-date/-p       Data ritiro "YYYY-MM-DD"
--periods/-d         Una o più durate (interi) in giorni
--global-json/-g     (facolt.) path a global_params.json
                     (default: ./global_params.json)
"""

from __future__ import annotations

import sys
# Se non è già UTF-8 rimpiazza il codec dello stdout
if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import argparse
import copy
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

# import degli step esistenti
from step_1 import step_1
from step_2 import step_2
from step_3 import step_3
from step_5 import step_5
from gen_output_file import gen_output_file


# ────────────────────────────────────────────────────────────────────────────
# FUNZIONI
# ────────────────────────────────────────────────────────────────────────────
def run_workflow(location: str, pick_date: str, periods: List[int],
                 global_json: Path) -> None:
    """Esegue tutti gli step per ciascuna durata in *periods*."""
    if not global_json.exists():
        raise FileNotFoundError(f"{global_json} non trovato.")

    base_settings = json.loads(global_json.read_text("utf-8"))
    base_settings["location"]  = location
    base_settings["pick_date"] = pick_date

    fmt = "%Y-%m-%d"
    dt_pick = datetime.strptime(pick_date, fmt)

    for days in periods:
        dt_drop = dt_pick + timedelta(days=days)
        drop_date = dt_drop.strftime(fmt)

        settings = copy.deepcopy(base_settings)
        settings["drop_date"] = drop_date

        print(f"\n→ Periodo {days} giorni  ({pick_date} → {drop_date})")
        # step-1 richiede argomenti espansi
        step_1(**settings)
        # gli altri accettano direttamente il dict
        step_2(settings)
        step_3(settings)
        step_5(settings)

    # genera file di confronto a fine ciclo
    gen_output_file(base_settings)
    print("\n✓ Workflow completato per tutti i periodi!")


# ────────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────────
def get_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="multi_period_cli",
        description="Esegue il workflow DiscoverCars per più durate."
    )
    parser.add_argument("-l", "--location", required=True,
                        help="Località (es. 'Naples Airport (NAP)')")
    parser.add_argument("-p", "--pick-date", required=True,
                        help="Data di ritiro YYYY-MM-DD")
    parser.add_argument("-d", "--periods", required=True, nargs="+", type=int,
                        help="Uno o più interi: numero di giorni di noleggio")
    parser.add_argument("-g", "--global-json", type=Path,
                        default=Path("global_params.json"),
                        help="Path a global_params.json (default: ./global_params.json)")
    return parser


def main() -> None:
    parser = get_cli_parser()
    args = parser.parse_args()

    run_workflow(
        location=args.location,
        pick_date=args.pick_date,
        periods=args.periods,
        global_json=args.global_json
    )


if __name__ == "__main__":
    main()
