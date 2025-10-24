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

    def compute_embeddings_for_procedure_node(self):
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
                coalesce(p.descripcion, '') AS descripcion
            WITH p,
                'Área: ' + area + '\n' +
                'Categoría: ' + categoria + '\n' +
                'Procedimiento: ' + nombre + '\n' +
                'Descripción del procedimiento: ' + descripcion AS texto
            RETURN elementId(p) AS eid,
                labels(p)    AS labels,
                properties(p) AS props,
                texto        AS embedding_text
            """

            results = self.db.run_read(query)
            
            for r in results:
                eid = r.get("eid")
                logging.info(f"---TEXTO FOR EMBEDDINGS---: {r}")
                # clean_text = self._clean_text(r)
                # logger.info(f"---{clean_text}---")
                # vector = self.embedding_generator.embed_query(clean_text)
                # self.db.run_write(
                #     """
                #     MATCH (n) WHERE elementId(n) = $id
                #     SET n.embedding = $vector
                #     """,
                #     parameters = {
                #     "id": eid, 
                #     "vector": vector
                # }
                # )


            self.db.close()
        except Exception as e:
            logging.error(f"Error computing embeddings for nodes: {e}")

    def _clean_text(self, res:Dict):
        """
        This method cleans the result of an input query to avoid incluiding
        in the embeddings generation embeddings 
        """
        #remove CommonLabel from labels
        clean_labels = [l for l in res.get("labels") if l != "CommonLabel"]
        label_text = " ".join(clean_labels)

        #extract properties
        props = res.get("props", {})
        nombre = props.get("nombre", "").strip() if isinstance(props.get("nombre"), str) else ""
        content = props.get("content")

        if isinstance(content, list):
            content = " ,".join(str(x).strip() for x in content if str(x).strip())
        
        elif isinstance(content, (int, float, bool)):
            content = str(content).strip()

        elif isinstance(content, str):
            content = str(content).strip()
        
        #join labels and properties on a unified text
        if nombre and content:
            clean_result = f"{label_text}: {nombre} - {content}"
        elif nombre:
            clean_result = f"{label_text}: {nombre}"
        elif content:
            clean_result = f"{label_text}: {content}"
        else:
            clean_result = label_text  
        return clean_result
    
    
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


node_embbeder = NodeEmbedder()
node_embbeder.compute_embeddings_for_all_nodes()


        
        
    
