::[Bat To Exe Converter]
::
::YAwzoRdxOk+EWAnk
::fBw5plQjdG8=
::YAwzuBVtJxjWCl3EqQJgSA==
::ZR4luwNxJguZRRnk
::Yhs/ulQjdF+5
::cxAkpRVqdFKZSDk=
::cBs/ulQjdF+5
::ZR41oxFsdFKZSDk=
::eBoioBt6dFKZSDk=
::cRo6pxp7LAbNWATEpCI=
::egkzugNsPRvcWATEpCI=
::dAsiuh18IRvcCxnZtBJQ
::cRYluBh/LU+EWAnk
::YxY4rhs+aU+JeA==
::cxY6rQJ7JhzQF1fEqQJQ
::ZQ05rAF9IBncCkqN+0xwdVs0
::ZQ05rAF9IAHYFVzEqQJQ
::eg0/rx1wNQPfEVWB+kM9LVsJDGQ=
::fBEirQZwNQPfEVWB+kM9LVsJDGQ=
::cRolqwZ3JBvQF1fEqQJQ
::dhA7uBVwLU+EWDk=
::YQ03rBFzNR3SWATElA==
::dhAmsQZ3MwfNWATElA==
::ZQ0/vhVqMQ3MEVWAtB9wSA==
::Zg8zqx1/OA3MEVWAtB9wSA==
::dhA7pRFwIByZRRnk
::Zh4grVQjdCyDJGyX8VAjFBJaSgu+GG6pDaET+NTs4PiMnV4NVeE6RJ3eyrudKfQc+EzhZqo7335fl4YNAhpUZwGifUI1rmtMoliMOdSIsgPtBE2R4ys=
::YB416Ek+ZG8=
::
::
::978f952a14a936cc963da21a135fa983
@echo off
REM Crea l'ambiente virtuale con Python 3.10 nella cartella "venv"
C:\Users\info\AppData\Local\Programs\Python\Python310\python.exe -m venv .venv

REM Attiva l'ambiente virtuale
call .venv\Scripts\activate.bat

REM Aggiorna pip all'ultima versione
python -m pip install --upgrade pip

REM Installa le dipendenze dal file requirements.txt
pip install -r requirements.txt

pip install playwright pytest-playwright -U
python -m playwright install


echo Ambiente configurato con successo!
pause
