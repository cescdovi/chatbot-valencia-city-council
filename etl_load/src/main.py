import logging

from config.setup_logging import setup_logging
from config.common_settings import settings

from etl_load.src.scrape_hacienda_links import scrape_hacienda_links
from etl_load.src.neo4j_loader import Neo4jConfig, Neo4jLoader
from etl_load.src.node_embedder import NodeEmbedder

def main():
    setup_logging()
    log = logging.getLogger(__name__)

    #scrape_hacienda_links()

    # config = Neo4jConfig()
    # loader = Neo4jLoader(config)

    #loader.create_constraints()
    #loader.set_common_label()

    # #generate embeddings for all nodes
    node_embbeder = NodeEmbedder()
    node_embbeder.compute_embeddings_for_procedure_nodes()
    node_embbeder.create_vector_index()


if __name__ == "__main__":

    main()
