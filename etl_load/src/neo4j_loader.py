import logging
from neo4j import GraphDatabase
from dataclasses import dataclass, field
from typing import List, Dict, Any
from config.common_settings import settings
from config.setup_logging import setup_logging

from etl_load.src.pydantic_model import Areas
from etl_load.src.pydantic_model import AreaModel, CategoryModel, ProcedureModel, Areas

setup_logging()
logger = logging.getLogger(__name__)

@dataclass
class Neo4jConfig:
    uri: str = settings.BOLT_URI_NEO4J
    user: str = settings.DATABASE_NEO4J_USER
    password: str = settings.DATABASE_NEO4J_PASSWORD
    database: str = settings.DATABASE_NEO4J_NAME


class Neo4jLoader:
    def __init__(self, config: Neo4jConfig) -> None:
        self.config = config
        self._driver = None

    def connect(self) -> None:
        """Establish a connection to the Neo4j database."""
        if self._driver is None:
            self._driver = GraphDatabase.driver(
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
    
    def run_read(self, query: str, parameters: dict = None) -> list[dict]:
        if self._driver is None:
            raise RuntimeError("Neo4j driver is not connected. Call connect() first.")
        with self._driver.session(database=self.config.database) as session:
            return session.execute_read(lambda tx: tx.run(query, parameters or {}).data())

    def run_write(self, query: str, parameters: dict = None):
        if self._driver is None:
            raise RuntimeError("Neo4j driver is not connected. Call connect() first.")
        with self._driver.session(database=self.config.database) as session:
            return session.execute_write(lambda tx: tx.run(query, parameters or {}).consume())


    
    def _save_area_to_neo4j(self, 
                            area_title: str
                            ) -> None:
        """
        Save a single Area to Neo4j"
        """
        cypher_query = """
        MERGE (a: Area {nombre: $area_title})
        """
        parameters = {"area_title": area_title}
        
        try:
            self.run_write(cypher_query, parameters)
            logging.info(f"Area '{area_title}' saved to Neo4j.")
        except Exception as e:
            logging.error(f"Failed to save area '{area_title}' to Neo4j: {e}")
    
    def _save_category_to_neo4j(self, 
                                area_title:str,
                                category_name:str,
                                category_url:str
                                ):
        """
        Save a category into Neo4j
        """
        cypher_query = """
        MATCH (a:Area {nombre: $area_title})
        MERGE (c:Categoria {nombre: $nombre})
        ON CREATE SET c.url = $url
        MERGE (a)-[:TIENE_CATEGORIA]->(c)
        """

        parameters = {
            "area_title": area_title,
            "nombre": category_name,
            "url": category_url

            }
        try:
            self.run_write(cypher_query, parameters)
            logging.info(f"Category '{category_name}' saved to Neo4j.")

        except Exception as e:
            logging.error(f"Failed to save category '{category_name}' to Neo4j: {e}")

    def _save_procedure_to_neo4j(self, 
                                 area_title:str,
                                 category_name:str,
                                 procedures_list: List[ProcedureModel] 

                                ):
        """
        Save a category into Neo4j
        """
        procedures_list_of_dicts = [p.model_dump() for p in procedures_list]

        cypher_query = """
        // 1. Matchear el area y categoria correspondiente
        MATCH (a:Area {nombre: $area_title})-[:TIENE_CATEGORIA]->(c:Categoria {nombre: $category_name})

        // 2. Iterar sobre la lista de procedures (list of dicts)
        WITH c, $procedures_list_of_dicts AS list
        UNWIND range(0, size(list)-1) AS idx
        WITH c, list[idx] AS procData, idx

        MERGE (c)-[r:TIENE_PROCEDIMIENTO]->(p:Procedimiento {nombre: procData.title})
        ON CREATE SET
            p.content = procData.content   // array de párrafos
        ON MATCH SET
            p.content = procData.content   // actualización idempotente

        """

        parameters = {
            "area_title": area_title,
            "category_name": category_name,
            "procedures_list_of_dicts": procedures_list_of_dicts,
            }
        try:
            self.run_write(cypher_query, parameters)
            logging.info(f"Procedure '{category_name}' saved to Neo4j.")

        except Exception as e:
            logging.error(f"Failed to save procedure '{category_name}' to Neo4j: {e}")
    
    def set_common_label(self):
        """
        Set a common label for all entities in the graph named "Node"
        to build a unique index for the graph.
        This is done to avoid having to create a unique index for each entity type.
        """

        try:
            self.connect()
            self.run_write(
                """
                MATCH (n)
                WHERE any(lbl IN labels(n) WHERE lbl IN [
                'Area','Categoria','Procedimiento'
                ])
                SET n:CommonLabel;
                """
            )
            self.close()
        
        except Exception as e:
            logging.error(f"Failed generating a common label for all nodes: {e}")
    
            
      
    
if __name__ == "__main__":
    config = Neo4jConfig()
    loader = Neo4jLoader(config)
    try:
        loader.connect()
        loader.run_write("""
                        MATCH (n) DETACH DELETE n
                        """)

#         # loader.set_common_label()
#         # records = loader.run_read("""
#         #                           MATCH (n:CommonLabel)
#         #                           WHERE n.embedding IS NULL
#         #                           RETURN labels(n) AS labels, properties(n) AS props
#         #                         """)
#         # logger.info(f"----type{type(records)}")
#         # logger.info(f"----RECORDS: {records[0]}----")
#         # logger.info("\n")
#         # logger.info(f"----RECORDS: {records[1]}----")
        logger.info("CONNECTED SUCCESFULLY")
        
    except Exception as e:
        logger.error(f"Error {e}")
        