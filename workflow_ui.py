#!/usr/bin/env python3
"""
Streamlit UI – esegue `workflow.py` (CLI) per più località/periodi e mostra
lo stdout/stderr in tempo reale dentro un riquadro tipo terminale.

Avvio:
    streamlit run streamlit_app.py
Prerequisiti:
    • playwright install chromium       # basta una volta sola
    • workflow.py deve trovarsi nella stessa cartella di questo file
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

import pandas as pd
import streamlit as st

# ────────────────────────────────────────────────────────────────────────────
# Costanti / helper
# ────────────────────────────────────────────────────────────────────────────
DEFAULT_OUTDIR = Path("output_data")
CLI_SCRIPT     = Path(__file__).with_name("workflow.py")  # script CLI

def _slugify(text: str) -> str:
    import unicodedata, re
    norm = unicodedata.normalize("NFKD", text)
    return re.sub(r"[^\w]+", "_", norm.encode("ascii", "ignore").decode()).strip("_").lower()


def build_csv_for_location(location: str, pick_date: str, out_dir: Path, periods: list, extra_periods: list):
    """Aggrega i prezzi in un CSV come prima; invariato rispetto alla versione precedente."""
    slug_loc = _slugify(location)
    base_dir = Path("data") / slug_loc
    if not base_dir.exists():
        st.warning(f"Dati non trovati per {location}")
        return

    period_dirs = sorted((d for d in base_dir.iterdir() if d.is_dir() and d.name.isdigit()),
                         key=lambda p: int(p.name))
    rows: dict[str, dict[int, float]] = {}
    periods: List[int] = []

    for pdir in period_dirs:
        days = int(pdir.name)
        json_path = pdir / pick_date / "group_selected_details.json"
        if not json_path.exists():
            continue
        periods.append(days)
        groups = json.loads(json_path.read_text("utf-8"))
        for g in groups:
            sipp = g.get("sipp_code")
            det  = g.get("selected_car_details") or {}
            pay_arr = det.get("pay_on_arrival") or 0
            pay_now = det.get("pay_now") or 0
            if pay_arr:
                price = round(pay_arr - 1, 2)
            elif pay_now:
                price = round(pay_now * 0.7 - 1, 2)
            else:
                continue
            rows.setdefault(sipp, {})[days] = price

    if not rows:
        st.warning(f"Nessun prezzo valido per {location}")
        return

    df = pd.DataFrame(rows).T.reindex(sorted(rows)).reindex(columns=sorted(periods))
    df.index.name, df.columns.name = "SIPP_Code", "Period_Days"

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"comparison_{slug_loc}_{pick_date}.csv"
    df.to_csv(out_path, float_format="%.2f", encoding="utf-8")
    st.success(f"CSV salvato: {out_path}")



def build_csv_for_location__(
    location: str,
    pick_date: str,
    out_dir: Path,
    periods: list[int],
    extra_periods: list[int],
):
    """
    Crea/aggiorna il CSV per *location*.

    • Colonne = periodi base (prezzo pieno) +
                colonne 'giorni extra' (costo medio per giorno aggiuntivo).
    • L’ordine segue i giorni in modo crescente.
    """
    import numpy as np

    slug_loc = _slugify(location)
    base_dir = Path("data") / slug_loc
    if not base_dir.exists():
        st.warning(f"Dati non trovati per {location}")
        return

    # ------------------------------------------------------------
    # 1) Raccolta prezzi da tutte le cartelle periodo disponibili
    # ------------------------------------------------------------
    rows: dict[str, dict[int, float]] = {}            # {sipp -> {days: price}}
    for pdir in base_dir.iterdir():
        if not (pdir.is_dir() and pdir.name.isdigit()):
            continue
        days = int(pdir.name)
        if days not in periods:                       # ignoriamo periodi non richiesti
            continue
        json_path = pdir / pick_date / "group_selected_details.json"
        if not json_path.exists():
            continue

        groups = json.loads(json_path.read_text("utf-8"))
        for g in groups:
            sipp = g.get("sipp_code")
            det  = g.get("selected_car_details") or {}
            pay_arr = det.get("pay_on_arrival") or 0
            pay_now = det.get("pay_now") or 0
            if pay_arr:
                price = round(pay_arr - 1, 2)
            elif pay_now:
                price = round(pay_now * 0.7 - 1, 2)
            else:
                continue
            rows.setdefault(sipp, {})[days] = price

    if not rows:
        st.warning(f"Nessun prezzo valido per {location}")
        return

    # ------------------------------------------------------------
    # 2) DataFrame prezzi base
    # ------------------------------------------------------------
    all_base_periods   = sorted(set(periods) - set(extra_periods))
    all_extra_periods  = sorted(extra_periods)
    df = (
        pd.DataFrame(rows)
        .T.reindex(sorted(rows))                      # indice SIPP ordinato
        .reindex(columns=all_base_periods)            # solo colonne base
    )
    df.index.name, df.columns.name = "SIPP_Code", "Period_Days"

    # ------------------------------------------------------------
    # 3) Calcolo colonne 'giorni extra'
    # ------------------------------------------------------------
    for ep in all_extra_periods:
        # trova il periodo base immediatamente precedente (max < ep)
        prev_candidates = [b for b in all_base_periods if b < ep]
        if not prev_candidates:
            continue                                  # nessun precedente → salto
        prev = max(prev_candidates)

        # Aggiungo temporaneamente la colonna ep (se non esiste) per poter leggere il prezzo
        if ep not in df.columns:
            df[ep] = np.nan

        # costo medio per giorno aggiuntivo
        diff_days = ep - prev
        serie_extra = (df[ep] - df[prev]) / diff_days

        # inserisco subito dopo la colonna ep con nome fisso 'giorni extra'
        insert_pos = list(df.columns).index(ep) + 1
        df.insert(insert_pos, "giorni extra", serie_extra)

    # ------------------------------------------------------------
    # 4) Scrittura CSV
    # ------------------------------------------------------------
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"comparison_{slug_loc}_{pick_date}.csv"
    df.to_csv(out_path, float_format="%.2f", encoding="utf-8")
    st.success(f"CSV salvato: {out_path}")


def build_csv_for_location_(
    location: str,
    pick_date: str,
    out_dir: Path,
    periods: list[int],
    extra_periods: list[int],
):
    """
    Genera il CSV:
      • colonne periodi BASE  → prezzo pieno (come prima)
      • colonne periodi EXTRA → costo medio per giorno aggiuntivo,
        sostituendo la colonna numerica con il nome fisso 'giorni extra'.
    """
    import numpy as np

    slug_loc = _slugify(location)
    base_dir = Path("data") / slug_loc
    if not base_dir.exists():
        st.warning(f"Dati non trovati per {location}")
        return

    # ------------------------------------------------------------
    # 1) Raccolta dei prezzi dai file JSON
    # ------------------------------------------------------------
    rows: dict[str, dict[int, float]] = {}          # {sipp_code: {days: price}}
    for pdir in base_dir.iterdir():
        if not (pdir.is_dir() and pdir.name.isdigit()):
            continue
        days = int(pdir.name)
        if days not in periods:                     # analizziamo solo i periodi richiesti
            continue

        json_path = pdir / pick_date / "group_selected_details.json"
        if not json_path.exists():
            continue

        groups = json.loads(json_path.read_text("utf-8"))
        for g in groups:
            sipp = g.get("sipp_code")
            det  = g.get("selected_car_details") or {}
            pay_arr = det.get("pay_on_arrival") or 0
            pay_now = det.get("pay_now") or 0
            if pay_arr:
                price = round(pay_arr - 1, 2)
            elif pay_now:
                price = round(pay_now * 0.7 - 1, 2)
            else:
                continue
            rows.setdefault(sipp, {})[days] = price

    if not rows:
        st.warning(f"Nessun prezzo valido per {location}")
        return

    # ------------------------------------------------------------
    # 2) Costruzione DataFrame con TUTTI i periodi richiesti
    # ------------------------------------------------------------
    all_periods_sorted = sorted(periods)            # base + extra, ordinati
    df = (
        pd.DataFrame(rows)
        .T
        .reindex(sorted(rows))                      # indice SIPP ordinato
        .reindex(columns=all_periods_sorted)        # colonne in ordine numerico
    )
    df.index.name, df.columns.name = "SIPP_Code", "Period_Days"

    # ------------------------------------------------------------
    # 3) Elaborazione dei periodi EXTRA
    # ------------------------------------------------------------
    base_periods   = sorted(set(periods) - set(extra_periods))
    for ep in sorted(extra_periods):
        # Trova il periodo BASE immediatamente precedente
        prev_candidates = [b for b in base_periods if b < ep]
        if not prev_candidates:
            continue                                # se non c’è un base precedente, salta
        prev = max(prev_candidates)

        # Calcola il costo medio per giorno aggiuntivo
        diff_days = ep - prev
        serie_extra = (df[ep] - df[prev]) / diff_days

        # Sovrascrive la colonna ep con la serie appena calcolata
        df[ep] = serie_extra

        # Rinomina la colonna ep in 'giorni extra'
        df.rename(columns={ep: "giorni extra"}, inplace=True)

        # Aggiorna la lista delle colonne ordinate
        col_list = list(df.columns)
        # (dopo il rename le colonne rimangono nella stessa posizione)

    # ------------------------------------------------------------
    # 4) Salvataggio CSV
    # ------------------------------------------------------------
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"comparison_{slug_loc}_{pick_date}.csv"
    df.to_csv(out_path, float_format="%.2f", encoding="utf-8")
    st.success(f"CSV salvato: {out_path}")




# ────────────────────────────────────────────────────────────────────────────
# Interfaccia Streamlit
# ────────────────────────────────────────────────────────────────────────────
st.title("DiscoverCars — orchestratore (output live)")

with st.form("params"):
    pick_date   = st.date_input("Data di ritiro", value=datetime(2025, 6, 10)).strftime("%Y-%m-%d")
    periods_in = st.text_input("Periodi BASE (giorni) – es: 1,3,7", "1,5,14")
    extra_in = st.text_input("Periodi EXTRA (facolt.) – es: 2,4 (lascia vuoto per calcolo automatico)", "2,10,20")

    locations_in= st.text_area("Località (una per riga)", "Naples Airport (NAP)")
    out_dir_in  = st.text_input("Cartella output CSV", str(DEFAULT_OUTDIR))
    run_btn     = st.form_submit_button("Esegui workflow")

if run_btn:
    # --- parsing ---
    try:
        periods = sorted({int(x) for x in periods_in.split(",") if x.strip()})
        extra_periods = sorted({int(x) for x in extra_in.split(",") if x.strip()})
        periods.extend(extra_periods)
        periods = sorted(set(periods))

        assert periods, "Nessun periodo valido"
    except Exception as exc:
        st.error(f"Periodi non validi: {exc}")
        st.stop()

    locations = [l.strip() for l in locations_in.splitlines() if l.strip()]
    if not locations:
        st.error("Inserisci almeno una località")
        st.stop()

    out_dir  = Path(out_dir_in).expanduser()
    total    = len(locations)
    progress = st.progress(0.0)

    for idx, loc in enumerate(locations, 1):
        st.header(f"🚗 {loc}")
        # placeholder “terminale” che si aggiorna riga per riga
        term_box = st.empty()          # container vuoto
        log_lines: List[str] = []

        # costruiamo la lista di argomenti per subprocess
        cmd = [
            sys.executable, "-u",  # ← -u = PYTHONUNBUFFERED=1
            str(CLI_SCRIPT),
            "--location", loc,
            "--pick-date", pick_date,
            "--periods", *map(str, periods)
        ]

        # avvio processo in modalità streaming
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,                 # line buffered
            universal_newlines=True    # stesso di text=True
        )

        # leggo stdout riga per riga e aggiorno la UI in tempo reale
        for line in proc.stdout:                           # :contentReference[oaicite:1]{index=1}
            log_lines.append(line.rstrip("\n"))
            # mostro massimo ~500 righe per non “appesantire” il browser
            term_box.code("\n".join(log_lines[-500:]), language="bash")

        proc.wait()
        exit_code = proc.returncode

        if exit_code == 0:
            st.success("Completato senza errori")
        else:
            st.error(f"CLI exit code {exit_code}")

        # genera CSV confronto
        build_csv_for_location(loc, pick_date, out_dir, periods, extra_periods)
        progress.progress(idx / total)

    st.success("Workflow terminato per tutte le località.")
