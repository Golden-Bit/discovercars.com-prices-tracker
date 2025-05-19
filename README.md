# Price Tracker DiscoverCars

Un **price tracker** che automatizza la ricerca e il monitoraggio dei prezzi di noleggio auto su DiscoverCars.com, consentendo di ottenere notifiche tempestive sulle variazioni delle tariffe.

## Descrizione

Questo progetto utilizza Playwright (o in alternativa Selenium) per:

* Navigare su DiscoverCars.com in modalità headful o headless.
* Compilare i parametri di ricerca (località, date, orari, età del guidatore).
* Estrare i risultati di prezzo attuali.
* Confrontare i prezzi nel tempo e generare report o inviare notifiche (email, webhook, ecc.).

## Funzionalità principali

* **Ricerca automatizzata**: invio periodico di query con parametri configurabili.
* **Monitoraggio storico**: salvataggio dei prezzi su database (es. SQLite o PostgreSQL).
* **Notifiche**: alert via email o integrazione con servizi di messaggistica quando il prezzo scende sotto una soglia.
* **Report**: esportazione in CSV o generazione di grafici di tendenza.

## Requisiti

* Python 3.8+
* pip
* Playwright 1.x
* Node.js (per installare i browser tramite Playwright)
* Librerie aggiuntive:

  * `playwright`
  * `pandas` (per report)
  * `sqlalchemy` (per persistenza opzionale)

## Installazione

1. Clonare il repository:

   ```bash
   git clone https://github.com/tuoutente/price-tracker-discovercars.git
   cd price-tracker-discovercars
   ```

2. Creare un ambiente virtuale e installare le dipendenze:

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. Installare i browser Playwright:

   ```bash
   playwright install
   ```

## Configurazione

Modifica il file `config.yaml` per:

* Impostare la località di pick-up (es. "Brindisi").
* Definire le date di ritiro e riconsegna.
* Specificare orari, età del guidatore e paese di residenza.
* Soglia di prezzo per le notifiche.
* Parametri di notifica (SMTP, webhook, ecc.).

Esempio di `config.yaml`:

```yaml
pickup_location: "Brindisi, Italy"
pickup_date: "2025-05-22"
dropoff_date: "2025-05-30"
pickup_time: "11:00"
dropoff_time: "11:00"
driver_age: "30-65"
price_threshold: 30.00
notifications:
  email:
    smtp_server: smtp.example.com
    port: 587
    user: tracker@example.com
    password: secret
    to: ["user1@example.com", "user2@example.com"]
```

## Esempio di utilizzo

Per eseguire una singola ricerca e salvare i risultati:

```bash
python discovercars_search.py --config config.yaml
```

Per avviare il price tracker in esecuzione periodica (cron, Docker, ecc.):

```bash
python price_tracker.py --config config.yaml --interval 3600
```

(dove `--interval` è l'intervallo in secondi tra due rilevazioni)

## Struttura del progetto

```
├── config.yaml           # file di configurazione
├── discovercars_search.py# script di ricerca singola
├── price_tracker.py      # runner con polling periodico
├── requirements.txt      # dipendenze Python
├── models.py             # definizione modelli database
├── notifier.py           # logica di notifica (email, webhook)
└── README.md             # questa documentazione
```

## Contribuire

1. Fork del repository
2. Crea un branch feature: `git checkout -b feature/nome-feature`
3. Committa le modifiche: `git commit -m "Aggiunge feature..."`
4. Pusha il branch: `git push origin feature/nome-feature`
5. Apri una Pull Request

## Licenza

Questo progetto è rilasciato sotto licenza MIT. Vedi `LICENSE` per i dettagli.

## Autori e contatti

* **Nome Cognome** – [tuoutente](https://github.com/tuoutente)
* **Email**: [email@example.com](mailto:email@example.com)

Per domande o segnalazioni, apri un'issue sul repository GitHub.
