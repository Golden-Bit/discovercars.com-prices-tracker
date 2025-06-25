from __future__ import annotations
from pathlib import Path
from typing import List

import pandas as pd


def process_extra_periods(
    csv_path: str | Path,
    base_periods: List[int],
    extra_periods: List[int],
    output_path: str | Path | None = None,
) -> pd.DataFrame:
    """
    Rielabora un CSV prodotto dallo script Streamlit.

    * Per ogni colonna appartenente a `extra_periods`:
        nuovo_val = (val_extra - val_prev) / (giorni_extra - giorni_prev)

    * Al termine rinomina tutte quelle colonne in «extra days».

    Parametri
    ----------
    csv_path : str | Path
        Percorso del CSV di origine.
    base_periods : list[int]
        Periodi “normali” (giorni) presenti come colonne nel CSV.
    extra_periods : list[int]
        Periodi “extra” (giorni) da trasformare.
    output_path : str | Path | None, default=None
        Se specificato, il CSV risultante viene scritto qui.

    Ritorna
    -------
    pd.DataFrame
        DataFrame con colonne “extra” trasformate e rinominate «extra days».
    """
    csv_path = Path(csv_path)
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV non trovato: {csv_path}")

    # ──────────────────────────────────────────────────────────────
    # 1) Caricamento
    # ──────────────────────────────────────────────────────────────
    df = pd.read_csv(csv_path, index_col=0)

    # normalizziamo gli header: se sono numeri salvati come stringhe -> int
    def _to_int(col):
        try:
            return int(col)
        except (TypeError, ValueError):
            return col

    df.columns = [_to_int(c) for c in df.columns]

    # ──────────────────────────────────────────────────────────────
    # 2) Trasformazione periodi extra
    # ──────────────────────────────────────────────────────────────
    for ep in extra_periods:
        if ep not in df.columns:
            raise ValueError(f"Periodo extra {ep} mancante nel CSV.")

        # periodo base immediatamente precedente (< ep)
        prev_candidates = [b for b in base_periods if b < ep and b in df.columns]
        if not prev_candidates:
            raise ValueError(f"Nessun periodo base precedente a {ep} giorni.")
        prev = max(prev_candidates)

        diff_days = ep - prev
        df[ep] = (df[ep] - df[prev]) / diff_days

    # ──────────────────────────────────────────────────────────────
    # 3) Rinomina colonne extra → "extra days"
    #    (pandas consente header duplicati; se preferisci distinguere
    #     aggiungi un suffisso, ad es. f"extra days ({ep})")
    # ──────────────────────────────────────────────────────────────
    rename_map = {ep: "extra days" for ep in extra_periods if ep in df.columns}
    df = df.rename(columns=rename_map)

    # ──────────────────────────────────────────────────────────────
    # 4) Salvataggio facoltativo
    # ──────────────────────────────────────────────────────────────
    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, float_format="%.4f", encoding="utf-8")

    return df



if __name__ == "__main__":
    base_periods = [1, 3, 5]
    extra_periods = [2, 8]

    df_new = process_extra_periods(
        csv_path="output_data/comparison_naples_airport_nap_2025-06-14.csv",
        base_periods=base_periods,
        extra_periods=extra_periods,
        output_path="output_data/comparison_naples_airport_nap_2025-06-14_processed.csv"
    )
    print(df_new.head())