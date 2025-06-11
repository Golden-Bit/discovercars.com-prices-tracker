#!/usr/bin/env python3
"""
FastAPI micro-service che espone gli step del workflow DiscoverCars.

Avvia con:
    uvicorn fastapi_service:app --host 0.0.0.0 --port 8000  --reload
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, FastAPI
from pydantic import BaseModel, Field

# ── import degli step originali ────────────────────────────────────────────
from step_1 import step_1
from step_2 import step_2
from step_3 import step_3
from step_5 import step_5

app = FastAPI(
    title="DiscoverCars Workflow API",
    description="Espone step_1 … step_5 come endpoint REST",
    version="1.0.0"
)

# ───────────────────────────────────────────────────────────────────────────
# Pydantic schema: impostazioni comuni a tutti gli step
# ───────────────────────────────────────────────────────────────────────────
class Settings(BaseModel):
    location   : str  = Field(..., example="Naples Airport (NAP)")
    pick_date: str = Field(..., pattern=r"\d{4}-\d{2}-\d{2}", example="2025-06-10")
    drop_date: str = Field(..., pattern=r"\d{4}-\d{2}-\d{2}", example="2025-06-13")
    headless   : bool = True
    slow_mo    : Optional[int] = Field(None, description="ms delay for Playwright")
    output_file: str  = "cars.json"
    car_group  : Optional[str] = None

# helper per salvare settings su disco (debug)
def _save_settings(tag: str, s: Settings):
    Path("settings_dumps").mkdir(exist_ok=True)
    Path(f"settings_dumps/{tag}.json").write_text(s.model_dump_json(), "utf-8")

# ───────────────────────────────────────────────────────────────────────────
#  ENDPOINTS
# ───────────────────────────────────────────────────────────────────────────
@app.post("/step1", summary="Esegue lo step 1 (scraping lista veicoli)")
def run_step1(settings: Settings, tasks: BackgroundTasks):
    _save_settings("step1", settings)
    # step 1 è asincrono → lo eseguiamo direttamente
    step_1(**settings.model_dump())
    return {"status": "step1 completed"}

@app.post("/step2", summary="Esegue lo step 2 (extract names)")
def run_step2(settings: Settings, tasks: BackgroundTasks):
    _save_settings("step2", settings)
    # step 2 è rapido: esecuzione sincrona
    step_2(settings.model_dump())
    return {"status": "step2 completed"}

@app.post("/step3", summary="Esegue lo step 3 (classificazione SIPP)")
def run_step3(settings: Settings, tasks: BackgroundTasks):
    _save_settings("step3", settings)
    step_3(settings.model_dump())
    return {"status": "step3 completed"}

@app.post("/step5", summary="Esegue lo step 5 (selezione veicolo e dettagli)")
def run_step5(settings: Settings, tasks: BackgroundTasks):
    _save_settings("step5", settings)
    step_5(settings.model_dump())
    return {"status": "step5 completed"}

@app.post("/run_all", summary="Esegue l’intero workflow in background")
async def run_all(settings: Settings, tasks: BackgroundTasks):
    """
    Lancia tutti gli step in sequenza in **background**.
    Il client ottiene subito risposta ⇒ evita timeout HTTP lunghi.
    """
    _save_settings("all", settings)

    async def _pipeline():
        step_1(**settings.model_dump())
        step_2(settings.model_dump())
        step_3(settings.model_dump())
        step_5(settings.model_dump())

    # FastAPI BackgroundTasks *non* gestisce coroutine ⇒ usiamo create_task
    loop = asyncio.get_event_loop()
    tasks.add_task(loop.create_task, _pipeline())
    return {"status": "pipeline scheduled"}
