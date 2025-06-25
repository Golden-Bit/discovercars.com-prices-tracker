#!/usr/bin/env python3
"""
csv_to_xlsx_static.py
─────────────────────
Piccolo script di utilità che converte un file CSV in un file Excel (XLSX).
Le vie d’ingresso/uscita sono impostate **qui sotto come variabili**—niente
argomenti da linea di comando.

Istruzioni:
    1. Modifica le variabili `CSV_PATH` e/o `XLSX_PATH` a tuo piacimento.
    2. Esegui:  python csv_to_xlsx_static.py
Prerequisiti:
    pip install pandas openpyxl   # o 'xlsxwriter', vedi EXCEL_ENGINE
"""

from __future__ import annotations

from pathlib import Path
import pandas as pd

# ────────────────────────────────────────────────────────────────────────────
# CONFIGURAZIONE SEMPLICE (modifica solo queste righe se ti serve)
# ────────────────────────────────────────────────────────────────────────────
CSV_PATH   = Path("output_data/comparison_naples_airport_nap_2025-06-30__1.csv")
XLSX_PATH  = CSV_PATH.with_suffix(".xlsx")      # oppure Path("result.xlsx")
EXCEL_ENGINE = "openpyxl"                       # o "xlsxwriter"
# ────────────────────────────────────────────────────────────────────────────


def convert_csv_to_excel(csv_path: Path, xlsx_path: Path, engine: str = EXCEL_ENGINE) -> None:
    """Legge *csv_path* in un DataFrame e lo salva in *xlsx_path*."""
    if not csv_path.exists():
        raise FileNotFoundError(f"{csv_path} non trovato")

    df = pd.read_csv(csv_path)
    xlsx_path.parent.mkdir(parents=True, exist_ok=True)      # crea cartella se manca
    df.to_excel(xlsx_path, index=False, engine=engine)
    print(f"✓ Convertito: {csv_path} → {xlsx_path}")


if __name__ == "__main__":
    convert_csv_to_excel(CSV_PATH, XLSX_PATH)
