# streamlit_app.py
"""
Streamlit UI per lanciare la workflow multi-periodo su più località
e generare un CSV di confronto.  Avvia con:
    streamlit run streamlit_app.py
"""

from __future__ import annotations

# ╭──────────────────────────────────────────────────────────────╮
# │  PATCH FONDAMENTALE — deve stare IN CIMA, prima di tutto.    │
# │  Impone WindowsSelectorEventLoopPolicy (che gestisce i       │
# │  subprocess) così Playwright può lanciare Chromium.          │
# ╰──────────────────────────────────────────────────────────────╯
import sys, asyncio
if sys.platform.startswith("win"):
    # se l'utente ha già fissato la policy la lasciamo stare
    if not isinstance(asyncio.get_event_loop_policy(),
                       asyncio.WindowsSelectorEventLoopPolicy):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ────────────────────────────────────────────────────────────────
#  IMPORT ora sicuri (Playwright verrà importato più tardi)
# ────────────────────────────────────────────────────────────────
import copy
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

import pandas as pd
import streamlit as st

from step_1_async import step_1_async      # nuova versione async
from step_2       import step_2
from step_3       import step_3
from step_5       import step_5            # rimane sync

# ────────────────────────────────────────────────────────────────────────────
# Costanti / helper
# ────────────────────────────────────────────────────────────────────────────
DEFAULT_OUTDIR = Path("data")

def _slugify(text: str) -> str:
    import unicodedata
    norm = unicodedata.normalize("NFKD", text)
    return re.sub(r"[^\w]+", "_", norm.encode("ascii", "ignore").decode()).strip("_").lower()

# ---------- CSV builder ----------
def build_csv_for_location(location: str, pick_date: str, out_dir: Path):
    slug_loc = _slugify(location)
    base_dir = Path("data") / slug_loc
    if not base_dir.exists():
        st.warning(f"Cartella {base_dir} non trovata – nessun CSV generato per {location}")
        return

    period_dirs = sorted(
        (d for d in base_dir.iterdir() if d.is_dir() and d.name.isdigit()),
        key=lambda d: int(d.name)
    )
    if not period_dirs:
        st.warning(f"Nessun periodo trovato per {location}")
        return

    periods_found: List[int] = []
    rows: dict[str, dict[int, float]] = {}

    for pdir in period_dirs:
        days = int(pdir.name)
        json_path = pdir / pick_date / "group_selected_details.json"
        if not json_path.exists():
            continue
        periods_found.append(days)
        groups = json.loads(json_path.read_text(encoding="utf-8"))
        for g in groups:
            sipp = g.get("sipp_code", "")
            det  = g.get("selected_car_details")
            if not (sipp and det):
                continue
            pay_now, pay_arr = det.get("pay_now"), det.get("pay_on_arrival")
            if pay_arr and pay_arr > 0:
                price = round(pay_arr - 1, 2)
            elif pay_now and pay_now > 0:
                price = round(pay_now * 0.7 - 1, 2)
            else:
                continue
            rows.setdefault(sipp, {})[days] = price

    if not rows:
        st.warning(f"Nessun prezzo valido per {location}")
        return

    df = pd.DataFrame(rows).T
    df = df.reindex(sorted(df.index))
    df = df[sorted(periods_found)]
    df.index.name   = "SIPP_Code"
    df.columns.name = "Period_Days"

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"comparison_{slug_loc}_{pick_date}.csv"
    df.to_csv(out_path, float_format="%.2f", encoding="utf-8")
    st.success(f"CSV salvato: {out_path}")

# ────────────────────────────────────────────────────────────────────────────
# Streamlit UI
# ────────────────────────────────────────────────────────────────────────────
st.title("Multi-period car-rental workflow")

with st.form("params"):
    pick_date    = st.date_input("Data di inizio (pick-up)",
                                 value=datetime(2025, 6, 10)).strftime("%Y-%m-%d")
    periods_in   = st.text_input("Periodi (giorni) – es: 1,2,3,7", value="3")
    locations_in = st.text_area("Località (una per riga)", value="Naples Airport (NAP)")
    out_dir_in   = st.text_input("Cartella output CSV (opzionale)",
                                 value=str(DEFAULT_OUTDIR))
    run_btn      = st.form_submit_button("Esegui workflow")

# ――― avvio pipeline ―――
if run_btn:
    # parsing input
    try:
        periods = [int(x.strip()) for x in periods_in.split(",") if x.strip()]
        assert periods, "Inserisci almeno un periodo valido."
    except Exception as e:
        st.error(f"Periodi non validi: {e}")
        st.stop()

    locations = [l.strip() for l in locations_in.splitlines() if l.strip()]
    if not locations:
        st.error("Devi specificare almeno una località.")
        st.stop()

    out_dir = Path(out_dir_in).expanduser() if out_dir_in else DEFAULT_OUTDIR

    base_settings = json.load(open("global_params.json", "r"))
    base_settings["pick_date"] = pick_date

    total_steps = len(locations) * len(periods)
    progress    = st.progress(0, text="Avvio…")
    done        = 0

    for loc in locations:
        base_settings["location"] = loc
        st.subheader(f"Località: **{loc}**")
        for days in periods:
            dt_drop = (datetime.strptime(pick_date, "%Y-%m-%d")
                       + timedelta(days=days)).strftime("%Y-%m-%d")
            settings = copy.deepcopy(base_settings)
            settings["drop_date"] = dt_drop

            st.write(f"• Periodo **{days}** giorni  ({pick_date} → {dt_drop})")

            # step-1 (async) – chiamato dentro run_until_complete
            asyncio.run(step_1_async(**settings))

            # step-2/3/5 (sync) in thread separato
            def run_sync_steps():
                step_2(settings)
                step_3(settings)
                step_5(settings)

            st.thread(run_sync_steps)  # Streamlit 1.32+ helper; per <1.32 usa threading.Thread

            done += 1
            progress.progress(done / total_steps)

        build_csv_for_location(loc, pick_date, out_dir)

    st.success("Workflow completato!")

