import logging
from neo4j import GraphDatabase, Driver
from dataclasses import dataclass, field

from config.common_settings import settings
from config.setup_logging import setup_logging


setup_logging()
logger = logging.getLogger(__name__)

@dataclass
class Neo4jConfig:
    uri: str = settings.BOLT_URI_NEO4J
    user: str = settings.DATABASE_NEO4J_USER
    password: str = settings.DATABASE_NEO4J_PASSWORD
    database: str = settings.DATABASE_NEO4J_NAME


class Neo4jExtractor:
    def __init__(self, config: Neo4jConfig) -> None:
        self.config = config
        self._driver = None

    def connect(self) -> None:
        """Establish a connection to the Neo4j database."""
        if self._driver is None:
            self._driver = GraphDatabase.Driver(
                self.config.uri,
                auth=(self.config.user, self.config.password)
            )
        self._driver.verify_connectivity()
        logging.info("Neo4j connection successful.")

    def close(self) -> None:
        """Close the Neo4j connection."""
        if self._driver:
            self._driver.close()
            logging.info("Neo4j connection closed.")
            self._driver = None
    
    def run_query(self, query: str, parameters: dict = None) -> list:
        """Run a Cypher query and return the results."""
        if self._driver is None:
            raise RuntimeError("Neo4j driver is not connected. Call connect() first.")
        
        with self._driver.session(database = self.config.database) as session:
            try:
                result = session.run(query, parameters)
            
            except Exception as e:
                logging.error(f"Error running query: {e}")
                raise
    
    def _save_to_neo4j_pydantic(self, area_title: str, category_model: Category) -> None:
    """Guarda la información validada por Pydantic en Neo4j."""
    
    # Usar .dict() para convertir el modelo Pydantic a un diccionario fácil de pasar a Cypher
    category_data = category_model.dict()

    logging.info(f"Saving validated Category '{category_model.name}' to Neo4j.")
    
    # 1. Crear o actualizar el AREA y la CATEGORY
    query_category = """
    MERGE (a:Area {name: $area_title})
    MERGE (c:Category {name: $category_name})
    ON CREATE SET c.url = $category_url, c.last_scraped = datetime()
    ON MATCH SET c.url = $category_url, c.last_scraped = datetime()
    MERGE (a)-[:CONTAINS]->(c)
    """
    self.db.execute_query(query_category, {
        "area_title": area_title, 
        "category_name": category_model.name, 
        "category_url": str(category_model.url) # Convertir HttpUrl a str
    })

    # 2. Iterar y crear Detalles (ProcedureDetail)
    for detail in category_model.procedures_details:
        detail_query = """
        MATCH (c:Category {name: $category_name})
        MERGE (d:ProcedureDetail {title: $title, content: $content})
        MERGE (c)-[:HAS_DETAIL]->(d)
        """
        self.db.execute_query(detail_query, {
            "category_name": category_model.name, 
            "title": detail.title, 
            "content": detail.content # Neo4j acepta listas de strings
        })
        
    # 3. Iterar y crear Información de Oficinas (OfficeInfo)
    for office in category_model.offices_info:
        info_query = """
        MATCH (c:Category {name: $category_name})
        MERGE (o:OfficeInfo {title: $title, content: $content})
        MERGE (c)-[:HAS_OFFICE_INFO]->(o)
        """
        self.db.execute_query(info_query, {
            "category_name": category_model.name, 
            "title": office.title, 
            "content": office.content
        })
