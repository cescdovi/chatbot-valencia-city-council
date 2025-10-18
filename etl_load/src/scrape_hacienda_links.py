import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
import os
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, TimeoutError as PlaywrightTimeoutError
from pydantic import BaseModel, Field, HttpUrl, TypeAdapter # Importamos Pydantic

from config.setup_logging import setup_logging
from config.common_settings import settings
from etl_load.src.neo4j_loader import Neo4jLoader, Neo4jConfig
from etl_load.src.pydantic_model import AreaModel, CategoryModel, ProcedureModel, Areas

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
    results: Areas = field(default_factory=lambda: Areas(areas=[])) 
    db_neo4j:Neo4jLoader = field(default_factory=lambda: Neo4jLoader(Neo4jConfig()))


    def start(self) -> None:
        """Start the Playwright browser and navigate to the base URL."""
        logging.info("Initializing Chromium browser...")
        self.browser = self.playwright.chromium.launch(headless=self.config.headless)
        self.page = self.browser.new_page()
        self.goto(settings.HACIENDA_URL)

        try:
            self.db_neo4j.connect()
        except Exception as e:
            logging.error(f"Could not connect to Neo4j: {e}")
        

        logging.info(f"Landing URL: {self.page.url}")
    
    def close(self) -> None:
        """Close the Playwright browser."""
        if self.browser:
            logging.info("Closing the browser...")
            self.browser.close()
        if self.db_neo4j:
            self.db_neo4j.close()

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


    def scrape_category(self, area_title: str, area_index:int, category_name: str, category_url: str) -> None:
        if not category_url:
            logging.warning(f"Category without href under '{area_title}'")
            return
        
        full_category_url = settings.BASE_URL + category_url
        logging.info(f"Opening category: {category_name} -> {category_url}")
        self.goto(full_category_url)

        current_category_data = {
            "category_name": category_name,
            "category_url": full_category_url,
            "procedures": [] 
        }
        
        procedures_list: List[ProcedureModel] = []
        
        raw_procedures = self.page.locator("div.txtProc")
        total = raw_procedures.count()
        general_limit = max(0, total - 2)

        # 2. Extracción de información general
        for j in range(general_limit):
            proc = raw_procedures.nth(j)
            if proc.locator("div.rotuloDetalleProc").count():
                procedure_title = proc.locator("div.rotuloDetalleProc").inner_text()
                procedure_content = proc.locator("div.descWebProc p, div.descWebProc li")
                content_list: List[str] = []
                for k in range(procedure_content.count()):
                    texts = procedure_content.nth(k).all_inner_texts()
                    for t in texts:
                        t = t.strip()
                        if t:
                            content_list.append(t)
                
                # CREACIÓN Y VALIDACIÓN DEL MODELO PYDANTIC
                procedures_list.append(ProcedureModel(
                    title=procedure_title, 
                    content=content_list
                ))
                logging.info(f"  Procedure: {procedure_title} ({len(content_list)} items)")
        
        # 3. Extracción de información de oficinas
        for j in range(general_limit, total):
            proc = raw_procedures.nth(j)
            if proc.locator("div.rotuloDetalleProcSmall").count():
                office_title = proc.locator("div.rotuloDetalleProcSmall").inner_text()
                items = proc.locator("div.oficinasLista li")
                offices_info: List[str] = []
                for m in range(items.count()):
                    t = items.nth(m).inner_text().strip()
                    if t:
                        offices_info.append(t)
                
                # CREACIÓN Y VALIDACIÓN DEL MODELO PYDANTIC
                procedures_list.append(ProcedureModel(
                    title=office_title, 
                    content=offices_info
                ))
                logging.info(f"  Offices: {office_title} ({len(offices_info)} items)")
        
        # 4. Asignar la lista de modelos de procedimientos
        current_category_data["procedures"] = procedures_list
    
        try:
            self.db_neo4j._save_procedure_to_neo4j(area_title,
                                                   category_name,
                                                   procedures_list)
        
        except Exception as e:
            logging.error(f"Failed to save procedure '{category_name}' to Neo4j: {e}") 

        
        # 5. CREACIÓN Y ASIGNACIÓN FINAL DEL MODELO PYDANTIC DE CATEGORÍA
        try:
            
            category_model = CategoryModel(**current_category_data)
            self.results.areas[area_index].categories.append(category_model)
            #logging.info(f"Category info '{category_name}' added to area '{area_title}'")
            logging.info(f"Category info '{category_name}' added")
        except Exception as e:
            logging.error(f"Error validating Pydantic model for category '{category_name}': {e}")

        self.persist()

        self.back_to_base()
    


    def scrape_area(self, area_index: int, areas_count: int) -> None:
        areas = self.list_areas()
        area = areas.nth(area_index)
        area_title = area.locator("div.rotuloDetalleProc").inner_text()
        logging.info(f"Processing area [{area_index+1}/{areas_count}]: {area_title}")

        # initialize area in results
        new_area_model = AreaModel(area_title=area_title, categories=[])
        self.results.areas.append(new_area_model)

        # save area to Neo4j immediately
        self.db_neo4j._save_area_to_neo4j(new_area_model.area_title)

        # expand area and list categories
        self.expand_area(area)
        categories = self.list_categories_in_area(area)
        categories_count = categories.count()
        if categories_count == 0:
            logging.warning(f"No categories found under area: {area_title}")
            return

        logging.info(f"{categories_count} categories found in area '{area_title}'")
        for category_index in range(categories_count):
            cat = categories.nth(category_index)
            category_name = (cat.inner_text()).strip()
            category_url = cat.get_attribute("href")

            self.db_neo4j._save_category_to_neo4j(new_area_model.area_title,
                                                  category_name,
                                                  category_url)
            
            # scrape each category of the area
            self.scrape_category(area_title, area_index, category_name, category_url)

    def persist(self) -> None:
        """Store results to a JSON file."""
        os.makedirs(self.results_dir.parent, exist_ok=True)
        with open(self.results_dir, "w", encoding="utf-8") as f:
            f.write(self.results.model_dump_json(indent=2))



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
    

       
def scrape_hacienda_links(headless: bool = True):
    config = ScraperConfig(headless=headless)
    with sync_playwright() as pw:
        scraper = Scraper(pw, config=config)
        scraper.run()
        return 