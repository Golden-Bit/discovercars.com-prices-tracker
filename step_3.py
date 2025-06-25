
#!/usr/bin/env python3
"""
build_gruppi_sipp_batch.py – doppio passaggio MANUAL/AUTOMATIC
───────────────────────────────────────────────────────────────
• 1° passaggio:   classifica tutti i modelli SOLO nei gruppi MANUAL
• 2° passaggio:   classifica di nuovo SOLO nei gruppi AUTOMATIC
   (dicendo al modello di ignorare la differenza di cambio)
• Merge finale:   per ciascun gruppo (sipp_code) la lista 'vehicles'
                  è l'unione dei modelli trovati nei due giri,
                  con score = max(score_manual, score_auto)
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys
from datetime import datetime
from itertools import islice
from pathlib import Path
from typing import Dict, Iterator, List, Tuple

# ────────────────────────────────────────────────────────────────────────────
# Helper slugify
# ────────────────────────────────────────────────────────────────────────────
def _slugify(text: str) -> str:
    import unicodedata
    norm = unicodedata.normalize("NFKD", text)
    return re.sub(r"[^\w]+", "_", norm.encode("ascii", "ignore").decode()).strip("_").lower()

# ────────────────────────────────────────────────────────────────────────────
# Config costanti
# ────────────────────────────────────────────────────────────────────────────
GRUPPI_BASE_FILE = Path("gruppi_sipp_base.json")
OPENAI_API_KEY = "..."
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

MODEL_NAME  = "gpt-4o"
TEMPERATURE = 0.2
BATCH_SIZE  = 15

# ────────────────────────────────────────────────────────────────────────────
# LangChain
# ────────────────────────────────────────────────────────────────────────────
try:
    from langchain_community.chat_models import ChatOpenAI
except ImportError:                 # LangChain < 0.2
    from langchain.chat_models import ChatOpenAI
from langchain.prompts import PromptTemplate

# ────────────────────────────────────────────────────────────────────────────
# Prompt (identico per i 2 passi, già esplicita di ignorare il cambio)
# ────────────────────────────────────────────────────────────────────────────
PROMPT_TMPL = """\
Sei un esperto di codici SIPP per il noleggio auto.

Ricevi:
1. Un array JSON di gruppi; ogni gruppo ha:
      • sipp_code     – codice SIPP
      • seats         – numero posti
      • examples      – lista di modelli che APPARTENGONO al gruppo
2. Una lista (≤ {batch_size}) di modelli da classificare.

**Ignora la differenza tra cambio MANUAL e AUTOMATIC** quando scegli
il gruppo: valuta solo dimensioni, segmento, numero posti, carrozzeria.

Restituisci *solo* un JSON array (stesso ordine dei modelli in input):

[
  {{"model": "<MODEL>", "sipp_code": "<CODICE_SIPP>", "score": 0.0-1.0}},
  …
]

Regole:
• Usa soltanto i sipp_code forniti.
• score = 1.0 se il modello coincide (case-insensitive) con uno degli
  "examples" del gruppo selezionato.
• Se non c'è match perfetto, assegnalo al gruppo più plausibile
  mettendo 0 < score < 1 proporzionale alla somiglianza.
• Nessun testo extra, nessun campo aggiuntivo.
Gruppi:
{groups_json}

Modelli:
{models_json}
"""
prompt = PromptTemplate.from_template(PROMPT_TMPL)

# ────────────────────────────────────────────────────────────────────────────
# Utilità
# ────────────────────────────────────────────────────────────────────────────
def chunked(seq: List[str], size: int) -> Iterator[List[str]]:
    it = iter(seq)
    while (chunk := list(islice(it, size))):
        yield chunk

def load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))

def save_json(obj, p: Path):
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def safe_json(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return ast.literal_eval(text)

def classify_batches(
    llm: ChatOpenAI,
    groups_subset: List[Dict],
    car_names: List[str]
) -> Dict[str, Dict[str, float]]:
    """
    Ritorna: { sipp_code -> { model -> score } } per i gruppi del subset.
    """
    buckets: Dict[str, Dict[str, float]] = {g["sipp_code"].upper(): {} for g in groups_subset}

    for b_idx, batch in enumerate(chunked(car_names, BATCH_SIZE), 1):
        print(f"    – batch {b_idx} ({len(batch)} modelli)")
        msg = prompt.format(
            batch_size=BATCH_SIZE,
            groups_json=json.dumps(groups_subset, ensure_ascii=False),
            models_json=json.dumps(batch, ensure_ascii=False),
        )
        raw = llm.predict(msg).strip()
        if "[" in raw and "]" in raw:
            raw = raw[raw.find("[") : raw.rfind("]") + 1]
        parsed = safe_json(raw)

        for itm in parsed:
            if not isinstance(itm, dict):
                continue
            mdl  = itm.get("model")
            code = itm.get("sipp_code", "").upper()
            scr  = itm.get("score")
            if mdl in batch and code in buckets and isinstance(scr, (int, float)):
                prev = buckets[code].get(mdl, 0)
                if scr > prev:
                    buckets[code][mdl] = float(scr)
    return buckets

# ────────────────────────────────────────────────────────────────────────────
# Merge manual/auto: unione set & max(score)
# ────────────────────────────────────────────────────────────────────────────
def merge_vehicle_maps(
    base: Dict[str, Dict[str, float]],
    add:  Dict[str, Dict[str, float]]
) -> Dict[str, Dict[str, float]]:
    out = {k: v.copy() for k, v in base.items()}
    for code, models in add.items():
        out.setdefault(code, {})
        for m, s in models.items():
            out[code][m] = max(out[code].get(m, 0.0), s)
    return out

# ────────────────────────────────────────────────────────────────────────────
# MAIN
# ────────────────────────────────────────────────────────────────────────────
def step_3(settings: dict):

    # 1. parametri globali -> work_dir
    loc, p_d, d_d = settings["location"], settings["pick_date"], settings["drop_date"]
    period = (datetime.strptime(d_d, "%Y-%m-%d") - datetime.strptime(p_d, "%Y-%m-%d")).days
    work_dir = Path("data") / _slugify(loc) / str(period) / p_d

    car_names_file = work_dir / "car_names.json"
    out_json       = work_dir / "gruppi_sipp.json"
    if not work_dir.exists():
        sys.exit(f"Cartella '{work_dir}' assente – esegui prima gli step precedenti.")
    if not GRUPPI_BASE_FILE.exists():
        sys.exit("gruppi_sipp_base.json mancante.")
    if not car_names_file.exists():
        sys.exit("car_names.json mancante.")

    print("→ carico gruppi base")
    raw_groups: List[Dict] = load_json(GRUPPI_BASE_FILE)
    # rinomino 'vehicles' → 'examples'
    for g in raw_groups:
        g["examples"] = g.pop("vehicles", [])

    # separo MANUAL / AUTOMATIC
    manual_groups   = [g for g in raw_groups if g.get("transmission", "").upper() == "MANUAL"]
    automatic_groups= [g for g in raw_groups if g.get("transmission", "").upper() == "AUTOMATIC"]

    # lista modelli
    car_names: List[str] = load_json(car_names_file)

    print(f"→ LLM: {MODEL_NAME}")
    llm = ChatOpenAI(model_name=MODEL_NAME, temperature=TEMPERATURE)

    # 2. classificazione sui gruppi MANUAL
    print("\n— PASSAGGIO 1: gruppi MANUAL —")
    buckets_manual = classify_batches(llm, manual_groups, car_names)

    # 3. classificazione sui gruppi AUTOMATIC
    print("\n— PASSAGGIO 2: gruppi AUTOMATIC —")
    buckets_auto   = classify_batches(llm, automatic_groups, car_names)

    # 4. merge (union + score max)
    buckets_final = merge_vehicle_maps(buckets_manual, buckets_auto)

    # 5. ricompongo output
    groups_out: List[Dict] = []
    for g in raw_groups:
        code = g["sipp_code"].upper()
        vehicles_list = [
            {"model": m, "score": round(s, 2)}
            for m, s in sorted(
                buckets_final.get(code, {}).items(),
                key=lambda x: (-x[1], x[0].lower())
            )
        ]
        g_out = g.copy()
        g_out["vehicles"] = vehicles_list
        groups_out.append(g_out)

    # 6. salvo
    work_dir.mkdir(parents=True, exist_ok=True)
    save_json(groups_out, out_json)
    print(f"\n✓ JSON finale scritto in '{out_json}'")

# ----------------------------------------------------------------------------

