from playwright.sync_api import sync_playwright

def run_search():
    with sync_playwright() as p:
        # 1) Avvia Chromium con GUI e rallenta leggermente per vedere le azioni
        browser = p.chromium.launch(headless=False, slow_mo=50)
        page = browser.new_page()

        # 2) Vai alla home di DiscoverCars
        page.goto("https://www.discovercars.com")

        # Se compare il banner cookie di OneTrust, accettalo
        try:
            page.click("#accept-recommended-btn-handler", timeout=5000)
        except:
            pass

        # 3) Inserisci la località di pick-up
        page.fill("#pick-up-location", "Brindisi")
        # Attendi che compaiano i suggerimenti e seleziona il primo
        page.wait_for_selector(".tt-dataset-locations .tt-suggestion", timeout=10000)
        page.click(".tt-dataset-locations .tt-suggestion")

        # 4) Imposta le date (formato YYYY-MM-DD) direttamente nei campi nascosti
        page.fill("#pick-date", "2025-05-22")
        page.fill("#drop-date", "2025-05-30")

        # 5) Seleziona l’orario (il <select> è nascosto ma funziona comunque)
        page.select_option("#pick-time", "11:00")
        page.select_option("#drop-time", "11:00")

        # 6) Avvia la ricerca
        page.click("#location-submit")

        # 7) Attendi che la pagina di risultati finisca di caricare
        page.wait_for_load_state("networkidle")

        # 8) Stampa il titolo della pagina e salva uno screenshot
        print("Titolo pagina risultati:", page.title())
        page.screenshot(path="discovercars_results.png", full_page=True)

        browser.close()

if __name__ == "__main__":
    run_search()
