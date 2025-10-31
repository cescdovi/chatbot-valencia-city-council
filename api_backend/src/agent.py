# from langchain.chains import RetrievalQA
# from langchain_core.tools import tool
# from langchain_openai import ChatOpenAI, OpenAIEmbeddings
# from langgraph.prebuilt import create_react_agent
# from langchain_neo4j import Neo4jVector
# from langchain_tavily import TavilySearch
# from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

# from langchain.chains import RetrievalQA
# from langchain.agents import create_react_agent, AgentExecutor
# from langchain.tools import tool
# from langchain.chat_models import ChatOpenAI
# from langchain.embeddings.openai import OpenAIEmbeddings

from langchain_neo4j import Neo4jVector, GraphCypherQAChain, Neo4jGraph
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain.agents import create_agent 
from langchain.tools import tool
from langchain_tavily import TavilySearch
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from config.common_settings import settings
from api_backend.src.agent_prompt import SYSTEM_AGENT_PROMPT, HUMAN_AGENT_PROMPT
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

# # create QA chain
# qa = RetrievalQA.from_chain_type(
#     llm=llm,
#     retriever=retriever,
#     chain_type="stuff",
#     verbose=True,
#     return_source_documents=True,
# )


####### TOOL 1: query Neo4j DB #######
@tool
def neo4j_query(query: str) -> str:
    """Realiza una búsqueda semántica en la base de datos Neo4j usando embeddings para encontrar nodos relevantes y genera una respuesta contextual basada en esos datos."""
    result = retriever.invoke(query)
    logging.info(f"Neo4j query tool invoked with query: {query}")
    return "\n\n".join(
        f"Source: {doc.metadata}\nContent: {doc.page_content}" 
        for doc in result
    )


####### TOOL 2: query Neo4j DB #######
#search_tool = TavilySearch(max_results=3, api_key=settings.TAVILY_API_KEY)

tavily_tool = TavilySearch(
    tavily_api_key=settings.TAVILY_API_KEY,
    max_results=2,
    #include_raw_content=True
)
@tool
def search_law(query: str) -> str:
    """Busca información sobre una ley en internet y devuelve un resumen en lenguaje sencillo. Usa esta herramienta cuando la respuesta devuelta por la base de datos incluya una ley"""
    results = tavily_tool.invoke(query)
    if results and len(results) > 0:
        return results[0]['content']  # o el campo que contenga el texto
    return "No se encontró información sobre la ley solicitada."



tools = [neo4j_query, search_law]

# brain that decides what to do and when to use each tool (but not executes them)
AGENT = create_agent(
    model = llm,
    tools = tools,
    system_prompt = SYSTEM_AGENT_PROMPT,
)

# for message_chunk, metadata in AGENT.stream(
#     {"messages": [{"role": "user", "content": "Que es un certificado IRPF?"}]},
#     stream_mode="messages"  # o "messages" para tokens individuales
# ):
#     if hasattr(message_chunk, "content"):
#         content = message_chunk.content
#     else:
#         content = None

#     response_metadata = getattr(message_chunk, "response_metadata", {})
#     usage_metadata = getattr(message_chunk, "usage_metadata", {})

#     # Mostrar información del chunk
#     #print("\n--- AGENT STREAM CHUNK ---")
#     print(f"Contenido: {repr(content)}")
#     #print(f"Response metadata: {response_metadata}")
#     #print(f"Metadata interno: {metadata}")
#     #print(f"Uso de tokens: {usage_metadata}")


for chunk in AGENT.stream(
    {"messages": [{"role": "user", "content": "tu pregunta"}]},
    stream_mode="updates"
):
    for node, data in chunk.items():
        if "messages" in data:
            for msg in data["messages"]:
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tool_call in msg.tool_calls:
                        print(f"Tool usada: {tool_call['name']}")
