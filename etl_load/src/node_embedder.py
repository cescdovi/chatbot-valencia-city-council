import logging
from typing import List, Dict

from etl_load.src.generate_embeddings import OpenAIEmbeddingsGenerator
from etl_load.src.neo4j_loader import Neo4jConfig, Neo4jLoader

from config.setup_logging import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

class NodeEmbedder:
    def __init__(self):
        self.db = Neo4jLoader(Neo4jConfig())
        self.embedding_generator = OpenAIEmbeddingsGenerator()

    def compute_embeddings_for_procedure_nodes(self):
        try: 
            self.db.connect()
            logging.info("Computing embeddings for procedures...")
            query = """
            MATCH (p:Procedimiento)
            WHERE p.embedding IS NULL
            OPTIONAL MATCH (c:Categoria)-[:TIENE_PROCEDIMIENTO]->(p)
            OPTIONAL MATCH (a:Area)-[:TIENE_CATEGORIA]->(c)
            WITH p, 
                coalesce(a.nombre, '')      AS area,
                coalesce(c.nombre, '')      AS categoria,
                coalesce(p.nombre, '')      AS nombre,
                coalesce(p.content, '')      AS descripcion

            WITH p,
                'Área: ' + area + '\n' +
                'Categoría: ' + categoria + '\n' +
                'Procedimiento: ' + nombre + '\n' +
                'Descripción del procedimiento: ' + descripcion AS texto
            RETURN elementId(p) AS eid,
                texto  AS text_to_embed
            """

            results = self.db.run_read(query)
            
            for r in results:
                eid = r.get("eid")
                logging.info(f"---TEXTO FOR EMBEDDINGS---: {r}")
                text_to_embed = r.get("text_to_embed")

                vector = self.embedding_generator.embed_query(text_to_embed)
                self.db.run_write(
                    """
                    MATCH (p:Procedimiento)
                    WHERE elementId(p) = $id
                    SET p.embedding = $vector
                    """,
                    parameters = {
                    "id": eid, 
                    "vector": vector
                }
                )


            self.db.close()
        except Exception as e:
            logging.error(f"Error computing embeddings for nodes: {e}")

    
    def create_vector_index(self):
        """
        Create vector index over embeddings for all entities (label Entity)
        """
        try:
            self.db.connect()

            self.db.run_write("""
                              CREATE VECTOR INDEX emb_index IF NOT EXISTS
                                FOR (p:Procedimiento) ON (p.embedding)
                                OPTIONS {
                                indexConfig: {
                                    `vector.dimensions`: 1536,
                                    `vector.similarity_function`: 'cosine'
                                }
                                };
            """)
            logging.info("Vector index 'emb_index' created successfully.")

            self.db.close()
        except Exception as e:
            logging.error(f"Error creating vector index: {e}")


# node_embbeder = NodeEmbedder()
# node_embbeder.compute_embeddings_for_procedure_node()


        
        
    
