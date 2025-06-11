@echo off
REM Spostati nella directory corrente (quella in cui si trova il BAT)
cd /d %~dp0

REM Attiva il virtual environment (assumendo che si trovi nella cartella "venv")
call .venv\Scripts\activate.bat

REM Avvia l'applicazione Streamlit usando lo script in app/ui.py
call python -m streamlit run workflow_ui.py

pause
