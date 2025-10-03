import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
import os
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, TimeoutError as PlaywrightTimeoutError
from config.setup_logging import setup_logging

from config.common_settings import settings

setup_logging()
logger = logging.getLogger(__name__)

@dataclass
class ScraperConfig:
    headless: bool = True
    nav_timeout_ms: int = 15000
    wait_until: str = "domcontentloaded"


@dataclass
class Scraper:
    playwright: Playwright
    config: ScraperConfig = field(default_factory=ScraperConfig)
    browser: Any = None
    page: Any = None
    results_dir: Path = field(default_factory=lambda: Path(settings.DATA_DIR) / "RESULTS.json")
    results: Dict = field(default_factory=dict)


    def start(self) -> None:
        """Start the Playwright browser and navigate to the base URL."""
        logging.info("Initializing Chromium browser...")
        self.browser = self.playwright.chromium.launch(headless=self.config.headless)
        self.page = self.browser.new_page()
        self.goto(settings.HACIENDA_URL)
        logging.info(f"Landing URL: {self.page.url}")
    
    def close(self) -> None:
        """Close the Playwright browser."""
        if self.browser:
            logging.info("Closing the browser...")
            self.browser.close()

    def goto(self, url: str) -> None:
        """Navigate to a specified URL with error handling."""
        logging.info(f"Navigating to: {url}")
        self.page.goto(url, wait_until=self.config.wait_until, timeout=self.config.nav_timeout_ms)
        logging.info(f"Current URL: {self.page.url}")
    
    def back_to_base(self) -> None:
        resp = self.page.go_back(wait_until=self.config.wait_until, timeout=self.config.nav_timeout_ms)
        if not resp:
            logging.warning("go_back() returned None; forcing return to BASE_URL")
            self.goto(settings.HACIENDA_URL)
        self.page.wait_for_url(settings.HACIENDA_URL, timeout=self.config.nav_timeout_ms)
        logging.info(f"Back at base: {self.page.url}")
    

    def list_areas(self):
        """List all areas on the main page (gestión tesorería...)."""
        return self.page.locator("div.listaProcedimientos div.itemDetalleProc")
    

    def expand_area(self, area):
        area.scroll_into_view_if_needed()
        area.click()
        self.page.wait_for_load_state(self.config.wait_until)
    


    def list_categories_in_area(self, area):
        return area.locator("div.cuerpoBusquedaProc a")



    def scrape_category(self, area_title: str, category_name: str, category_url: str) -> None:
        if not category_url:
            logging.warning(f"Category without href under '{area_title}'")
            return

        category_url = settings.BASE_URL + category_url
        logging.info(f"Opening category: {category_name} -> {category_url}")
        self.goto(category_url)

        procedures = self.page.locator("div.txtProc")
        total = procedures.count() #number of procedures
        general_limit = max(0, total - 2) # Exclude last two (offices info)

        # extract general info (without offices info)
        for j in range(general_limit):
            proc = procedures.nth(j)
            if proc.locator("div.rotuloDetalleProc").count():
                procedure_title = proc.locator("div.rotuloDetalleProc").inner_text() #Descripcion, quien puede solicitar, etc
                procedure_content = proc.locator("div.descWebProc p, div.descWebProc li") #contenido
                content: List[str] = []
                for k in range(procedure_content.count()):
                    texts = procedure_content.nth(k).all_inner_texts()
                    for t in texts:
                        t = t.strip()
                        if t:
                            content.append(t)
                self.results[area_title]["procedures"].append({procedure_title: content})
                logging.info(f"  Procedure: {procedure_title} ({len(content)} items)")
        
        # extract info from offices
        for j in range(general_limit, total):
            proc = procedures.nth(j)
            if proc.locator("div.rotuloDetalleProcSmall").count():
                office_title = proc.locator("div.rotuloDetalleProcSmall").inner_text()
                items = proc.locator("div.oficinasLista li")
                offices_info: List[str] = []
                for m in range(items.count()):
                    t = items.nth(m).inner_text().strip()
                    if t:
                        offices_info.append(t)
                self.results[area_title]["procedures"].append({office_title: offices_info})
                logging.info(f"  Offices: {office_title} ({len(offices_info)} items)")

        self.persist()

        # back to hacienda base url
        self.back_to_base()
    


    def scrape_area(self, index: int, areas_count: int) -> None:
        areas = self.list_areas()
        area = areas.nth(index)
        area_title = area.locator("div.rotuloDetalleProc").inner_text()
        logging.info(f"Processing area [{index+1}/{areas_count}]: {area_title}")

        # initialize area in results
        self.results.setdefault(area_title, {})
        self.results[area_title].setdefault("category_name", "")
        self.results[area_title].setdefault("category_url", "")
        self.results[area_title].setdefault("procedures", [])
        # expandir y listar categorías
        self.expand_area(area)
        categories = self.list_categories_in_area(area)
        categories_count = categories.count()
        if categories_count == 0:
            logging.warning(f"No categories found under area: {area_title}")
            return

        logging.info(f"{categories_count} categories found in area '{area_title}'")
        for c in range(categories_count):
            cat = categories.nth(c)
            category_name = (cat.inner_text()).strip()
            category_url = cat.get_attribute("href")
            
            self.results[area_title]['category_name'] = category_name
            self.results[area_title]['category_url'] = settings.BASE_URL+category_url

            self.persist()
            # scrape each category of the area
            self.scrape_category(area_title, category_name, category_url)

    def persist(self) -> None:
        """Store results to a JSON file."""
        os.makedirs(self.results_dir.parent, exist_ok=True)
        with open(self.results_dir, "w", encoding="utf-8") as f:
            json.dump(self.results, f, indent=4, ensure_ascii=False)



    def run(self) -> None:
        """Main method to run the scraper."""
        try:
            self.start()

            areas = self.list_areas()
            areas_count = areas.count()
            logging.info(f"Found {areas_count} areas on the page.")

            for i in range(areas_count):
                self.scrape_area(i, areas_count)

        except PlaywrightTimeoutError as te:
            logging.error(f"Timeout while loading the page: {te}")
        except Exception as e:
            logging.exception(f"An unexpected error occurred: {e}")
        finally:
            self.close()
       
with sync_playwright() as pw:
    scraper = Scraper(pw)
    scraper.run()




    


    



