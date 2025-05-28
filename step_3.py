#!/usr/bin/env python3
"""
build_gruppi_sipp_batch.py — FULL REWRITE
─────────────────────────────────────────
• Legge:
    - gruppi_sipp_base.json  (senza "vehicles")
    - data/naples_airport_nap_2025-05-29/car_names.json  (nomi unici)

• Suddivide i modelli in batch da 15, chiede a GPT-4o (o GPT-3.5) di
  assegnare il SIPP più vicino **e** di stimare un punteggio di affidabilità
  0-1.  Nessun codice “UNKNOWN”: se non c’è match perfetto, sceglie il più
  plausibile e dà score basso.

• Produce gruppi_sipp.json con:

    "vehicles": [
        { "model": "Fiat 500", "score": 1.0 },
        { "model": "Kia Picanto", "score": 0.8 },
        …
    ]
"""

from __future__ import annotations

import ast
import json
import os
from itertools import islice
from pathlib import Path
from typing import Dict, Iterator, List, Tuple

# ────────────────────────────────────────────────────────────────────────────
# CONFIG
# ────────────────────────────────────────────────────────────────────────────
GRUPPI_BASE_FILE = Path("gruppi_sipp_base.json")
CAR_NAMES_FILE   = Path("data/naples_airport_nap_2025-05-29/car_names.json")
OUTPUT_FILE      = Path("gruppi_sipp.json")

OPENAI_API_KEY = "sk-_____________"  # <— inserisci la tua
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

MODEL_NAME  = "gpt-4o"            # oppure "gpt-3.5-turbo-0125"
TEMPERATURE = 0.2
BATCH_SIZE  = 15

# ────────────────────────────────────────────────────────────────────────────
# IMPORT LangChain compatibili 0.1 / 0.2
# ────────────────────────────────────────────────────────────────────────────
try:
    from langchain_community.chat_models import ChatOpenAI
except ImportError:                          # < 0.2
    from langchain.chat_models import ChatOpenAI

from langchain.prompts import PromptTemplate

# ────────────────────────────────────────────────────────────────────────────
# PROMPT
# ────────────────────────────────────────────────────────────────────────────
PROMPT_TMPL = """\
Sei un esperto di codici SIPP.  
Ricevi:

1. Un array JSON di gruppi, con "sipp_code" e "example_vehicle".
2. Una lista (≤ 15) di modelli da classificare.

Restituisci **solo** un JSON array — stesso ordine dei modelli in input —:

[
  {{"model": "<MODEL>", "sipp_code": "<CODICE_SIPP>", "score": 0.0-1.0}},
  …
]

Regole:
• `sipp_code` non può essere "UNKNOWN": scegli il codice più vicino
  (segmento, dimensioni, cambio).  
• `score` è la tua confidenza (0.0 = molto incerto, 1.0 = corrispondenza
  perfetta con l’esempio).  
• Usa solo i `sipp_code` presenti nei gruppi.  
• Nessun altro testo, commento o chiave.
Gruppi:
{groups_json}

Modelli:
{models_json}
"""
prompt = PromptTemplate.from_template(PROMPT_TMPL)

# ────────────────────────────────────────────────────────────────────────────
# UTILITY
# ────────────────────────────────────────────────────────────────────────────
def chunked(seq: List[str], size: int) -> Iterator[List[str]]:
    it = iter(seq)
    while chunk := list(islice(it, size)):
        yield chunk


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj, path: Path):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def safe_json(text: str):
    """json.loads con fallback a ast.literal_eval."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return ast.literal_eval(text)

# ────────────────────────────────────────────────────────────────────────────
# LLM BATCH
# ────────────────────────────────────────────────────────────────────────────
def classify_batch(
    llm: ChatOpenAI, groups: List[Dict], models: List[str]
) -> Dict[str, Tuple[str, float]]:
    """
    Ritorna mapping:
        { model: (sipp_code, score_float) }  solo per modelli del batch.
    """
    msg = prompt.format(
        groups_json=json.dumps(groups, ensure_ascii=False),
        models_json=json.dumps(models, ensure_ascii=False),
    )
    raw = llm.predict(msg).strip()

    # estrai prima lista JSON
    if "[" in raw and "]" in raw:
        raw = raw[raw.find("[") : raw.rfind("]") + 1]

    parsed = safe_json(raw)

    mapping: Dict[str, Tuple[str, float]] = {}
    for item in parsed:
        if (
            isinstance(item, dict)
            and item.get("model") in models
            and isinstance(item.get("sipp_code"), str)
            and isinstance(item.get("score"), (int, float))
        ):
            mapping[item["model"]] = (item["sipp_code"].upper(), float(item["score"]))

    return mapping


# ────────────────────────────────────────────────────────────────────────────
# COSTRUZIONE BUCKETS / ENRICH
# ────────────────────────────────────────────────────────────────────────────
def build_buckets(groups: List[Dict]) -> Dict[str, List[Dict]]:
    return {g["sipp_code"].upper(): [] for g in groups}


def enrich_groups(groups: List[Dict], buckets: Dict[str, List[Dict]]):
    for g in groups:
        g["vehicles"] = sorted(
            buckets.get(g["sipp_code"].upper(), []),
            key=lambda x: (-x["score"], x["model"].lower()),
        )
    return groups


# ────────────────────────────────────────────────────────────────────────────
# MAIN
# ────────────────────────────────────────────────────────────────────────────
def main() -> None:
    groups_base = load_json(GRUPPI_BASE_FILE)
    car_names   = load_json(CAR_NAMES_FILE)

    llm = ChatOpenAI(model_name=MODEL_NAME, temperature=TEMPERATURE)
    buckets = build_buckets(groups_base)

    print(f"Classifico {len(car_names)} modelli in batch da {BATCH_SIZE}…")
    for i, batch in enumerate(chunked(car_names, BATCH_SIZE), 1):
        print(f"  • Batch {i} ({len(batch)} modelli)")
        mapping = classify_batch(llm, groups_base, batch)

        for model, (code, score) in mapping.items():
            if code in buckets:
                buckets[code].append({"model": model, "score": round(score, 2)})

    enriched = enrich_groups(groups_base, buckets)
    save_json(enriched, OUTPUT_FILE)
    print(f"✓ JSON finale con punteggi scritto in '{OUTPUT_FILE}'")


if __name__ == "__main__":
    main()
