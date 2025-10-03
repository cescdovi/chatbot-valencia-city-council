import logging
from playwright.sync_api import Playwright, sync_playwright, TimeoutError as PlaywrightTimeoutError
import json
from config.setup_logging import setup_logging


# Set up a logger 
setup_logging()
logger = logging.getLogger(__name__)


def run(playwright: Playwright):
    browser = None
    RESULTS = {}
    try:
        logging.info("Initializing Chromium browser...")
        chromium = playwright.chromium
        browser = chromium.launch(headless=True)  # set headless=True to run without UI

        logging.info("Opening a new page...")
        page = browser.new_page()

        url = "https://sede.valencia.es/sede/registro/indexM.xhtml?lang=1&m=HA"
        logging.info(f"Navigating to: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=15000)

        logging.info("Page loaded successfully.")
        logging.info(f"Current URL after first goto: {page.url}")


        # locate areas: gestion tesoreria, impuestos sobre actividades economicas, etc 
        areas = page.locator("div.listaProcedimientos div.itemDetalleProc")
        logging.info(f"Found {areas.count()} areas on the page.")

        for i in range(areas.count()):
            area = areas.nth(i)
            area_title = area.locator("div.rotuloDetalleProc").inner_text() #area title: gestion tesoreria, impuestos sobre actividades economicas
            logging.info(f"Processing area {i+1} of {areas.count()+1}: {area_title}")
            
            #init 
            RESULTS[area_title] = {}
            categories = area.locator("div.cuerpoBusquedaProc a") #list of "a" categories: [(devolucion proporcional IAE-COVID, URL)]

            if categories.count() == 0:
                logging.warning(f"No categories found under area: {area_title}")
                category_text = None
                category_href = None
            
            if categories.count() == 1:
                category_text = categories.inner_text() #category: gestion tesoreria
                category_href = categories.get_attribute("href") #url of gestion tesoreria
                logging.info(f"     Category name: {category_text}")
                logging.info(f"     Category URL: {category_href}")

                category_url = f"https://sede.valencia.es{category_href}"

                RESULTS[area_title]['category_text'] = category_text
                RESULTS[area_title]['category_url'] = category_href
                RESULTS[area_title]['procedures'] = [] # List to hold all procedures

                if category_href:
                    area.click()  # Expand area: ej: to access gestion tesoreria 
                    page.wait_for_load_state("domcontentloaded")
                          
                    page.goto(category_url, wait_until="domcontentloaded", timeout=15000)
                    logging.info(f"     Navigated to category URL: {page.url}")

                    #capture procedures in this category: descripcion, quien puede solicitarlo
                    procedures = page.locator("div.txtProc")

                    total_procs = procedures.count()
                    general_limit = max(0, total_procs - 2)  # exclude last two procedures (for offices)

                    # -----------------------------
                    # 1) Extract general procedures
                    # -----------------------------
                    for j in range(general_limit):
                        procedure = procedures.nth(j)

                        if procedure.locator("div.rotuloDetalleProc").count():
                            procedure_title = procedure.locator("div.rotuloDetalleProc").inner_text()
                            logging.info(f"  Procedure title: {procedure_title}")

                            nodes = procedure.locator("div.descWebProc p, div.descWebProc li")

                            content_list = []
                            for k in range(nodes.count()):
                                # all_inner_texts() returns a list
                                texts = nodes.nth(k).all_inner_texts()
                                content_list = [t if t.strip() else None for t in texts]

                            # store the results
                            RESULTS[area_title]['procedures'].append({procedure_title: content_list})
                            logging.info(f"    Procedure content: {content_list}")

                    # ----------------------------------------------------
                    # 2) Extract offices info (last 2 procedures)
                    # ----------------------------------------------------
                    for j in range(general_limit, total_procs):
                        procedure = procedures.nth(j)

                        if procedure.locator("div.rotuloDetalleProcSmall").count():
                            office_title = procedure.locator("div.rotuloDetalleProcSmall").inner_text()

                            offices_info_list = []
                            offices_items = procedure.locator("div.oficinasLista li")
                            for m in range(offices_items.count()):
                                office_text = offices_items.nth(m).inner_text().strip()
                                if office_text:
                                    offices_info_list.append(office_text)

                            # store offices info
                            RESULTS[area_title]['procedures'].append(
                                {
                                    office_title: offices_info_list
                                }
                            )

                        else:
                            logging.warning(f"Procedure section {j} under {area_title} did not match a known format.")

                                                    
                    
                    logging.info(f"Current URL after scrapping all procedures: {page.url}")
                    page.go_back(wait_until="domcontentloaded", timeout=15000)
                    logging.info(f"Back to previous page: {page.url}")
            
            if categories.count() > 1:
                for cat in range(categories.count()):
                    category = categories.nth(cat)
                    category_text = category.inner_text() #category: gestion tesoreria
                    category_href = category.get_attribute("href") #url of gestion tesoreria
                    logging.info(f"     Category name: {category_text}")
                    logging.info(f"     Category URL: {category_href}")

                    category_url = f"https://sede.valencia.es{category_href}"
                    RESULTS[area_title]["category_text"] = category_text
                    RESULTS[area_title]["category_url"] = category_href
                    RESULTS[area_title]['procedures'] = [] # List to hold all procedures

                    if category_href:
                        area.click()
                        page.wait_for_load_state("domcontentloaded")
                        page.goto(category_url, wait_until="domcontentloaded", timeout=15000)
                        logging.info(f"     Navigated to category URL: {page.url}")

                        #capture procedures in this category: descripcion, quien puede solicitarlo
                        procedures = page.locator("div.txtProc")
                        
                        total_procs = procedures.count()
                        general_limit = max(0, total_procs - 2)  # exclude last two procedures (for offices)

                        # -----------------------------
                        # 1) Extract general procedures
                        # -----------------------------
                        for j in range(general_limit):
                            procedure = procedures.nth(j)

                            if procedure.locator("div.rotuloDetalleProc").count():
                                procedure_title = procedure.locator("div.rotuloDetalleProc").inner_text()
                                logging.info(f"  Procedure title: {procedure_title}")

                                nodes = procedure.locator("div.descWebProc p, div.descWebProc li")

                                content_list = []
                                for k in range(nodes.count()):
                                    # all_inner_texts() returns a list
                                    texts = nodes.nth(k).all_inner_texts()
                                    content_list = [t if t.strip() else None for t in texts]

                                # store the results
                                RESULTS[area_title]['procedures'].append({procedure_title: content_list})
                                logging.info(f"    Procedure content: {content_list}")
                        
                            # ----------------------------------------------------
                            # 2) Extract offices info (last 2 procedures)
                            # ----------------------------------------------------
                            for j in range(general_limit, total_procs):
                                procedure = procedures.nth(j)

                                if procedure.locator("div.rotuloDetalleProcSmall").count():
                                    office_title = procedure.locator("div.rotuloDetalleProcSmall").inner_text()
                                    logging.info(f"  Offices title: {office_title}")

                                    offices_info_list = []
                                    offices_items = procedure.locator("div.oficinasLista li")
                                    for m in range(offices_items.count()):
                                        office_text = offices_items.nth(m).inner_text().strip()
                                        if office_text:
                                            offices_info_list.append(office_text)

                                    # store offices info
                                    RESULTS[area_title]['procedures'].append(
                                        {
                                            office_title: offices_info_list
                                        }
                                    )
        # Store the extracted procedure data
        with open("RESULTS.json", 'w', encoding='utf-8') as f:
            json.dump(RESULTS, f, indent=4, ensure_ascii=False)

    except PlaywrightTimeoutError as te:
        logging.error(f"Timeout while loading the page: {te}")
    except Exception as e:
        logging.exception(f"An unexpected error occurred: {e}")
    finally:
        if browser:
            logging.info("Closing the browser...")
            browser.close()

with sync_playwright() as playwright:
    run(playwright)