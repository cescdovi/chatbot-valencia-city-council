from langchain_neo4j import Neo4jVector
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain.agents import create_agent 
from langchain.tools import tool
from langchain_tavily import TavilySearch
from config.common_settings import settings
from api_backend.src.agent_prompt import SYSTEM_AGENT_PROMPT
import logging
# define LLM for as the agent brain
llm = ChatOpenAI(
    model=settings.LLM_MODEL,
    api_key=settings.OPENAI_API_KEY,
    streaming=True
)

# configure embeddings function
embeddings_function = OpenAIEmbeddings(
    model=settings.EMBEDDINGS_MODEL,
    api_key=settings.OPENAI_API_KEY,
)

# create vector store from Neo4j graph and load vector index
vectorstore = Neo4jVector.from_existing_graph(
    url=settings.BOLT_URI_NEO4J,
    username=settings.DATABASE_NEO4J_USER,
    password=settings.DATABASE_NEO4J_PASSWORD,
    database=settings.DATABASE_NEO4J_NAME,
    index_name="emb_index",
    embedding=embeddings_function,
    node_label="Procedimiento",
    text_node_properties=["nombre", "content"],
    embedding_node_property="embedding",
)

#create retriever from vector store
retriever = vectorstore.as_retriever(search_kwargs={"k": 1})

####### TOOL 1: query Neo4j DB #######
@tool
def neo4j_query(query: str) -> str:
    """Realiza una búsqueda semántica en la base de datos Neo4j usando embeddings para encontrar nodos relevantes y genera una respuesta contextual basada en esos datos."""
    result = retriever.invoke(query)
    logging.info(f"Neo4j query tool invoked with query: {query}")
    return ". ".join( 
        doc.page_content
        for doc in result
    )


####### TOOL 2: query Neo4j DB #######

tavily_tool = TavilySearch(
    tavily_api_key=settings.TAVILY_API_KEY,
    max_results=2,
    #include_raw_content=True
)
@tool
def search_law(query: str) -> str:
    """Busca información sobre una ley en internet y devuelve un resumen en lenguaje sencillo. Usa esta herramienta cuando la respuesta devuelta por la base de datos incluya una ley"""
    results = tavily_tool.invoke(query)
    logging.info(f"Search law tool invoked with query: {query}")
    return results



tools = [neo4j_query, search_law]

# brain that decides what to do and when to use each tool (but not executes them)
AGENT = create_agent(
    model = llm,
    tools = tools,
    system_prompt = SYSTEM_AGENT_PROMPT,
)
