#from langchain_redis import RedisChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
#from langchain_tavily import TavilySearch
from langchain_core.tools import tool
from langchain_neo4j import Neo4jVector
from langchain.chains import RetrievalQA

from config.common_settings import settings
from api_backend.src.agent_prompt import SYSTEM_AGENT_PROMPT, HUMAN_AGENT_PROMPT

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
    index_name="entity_emb",
    embedding=embeddings_function,
    node_label="Entity",
    text_node_properties=["text"],
    embedding_node_property="embedding",
)

#create retriever from vector store
retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

# create QA chain
qa = RetrievalQA.from_chain_type(
    llm=llm,
    retriever=retriever,
    chain_type="stuff",
    verbose=True,
    return_source_documents=True,
)


####### TOOL 1: query Neo4j DB #######
@tool
def neo4j_query(query: str) -> str:
    """Realiza una búsqueda semántica en la base de datos Neo4j usando embeddings para encontrar nodos relevantes y genera una respuesta contextual basada en esos datos."""
    result = qa.invoke({"query": query})
    return {
        "result": result["result"],
        "source_documents": [doc.page_content for doc in result["source_documents"]],
    }

tools = [neo4j_query]

AGENT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_AGENT_PROMPT),
    ("human", HUMAN_AGENT_PROMPT),
    MessagesPlaceholder(variable_name="agent_scratchpad"), #marks a spot in the prompt template where the agent inserts actions history
])

# brain that decides what to do and when to use each tool (but not executes them)
agent_runnable = create_tool_calling_agent(
    llm,
    tools,
    AGENT_PROMPT,
    # handle_parsing_errors=True,  # force agent to use tools
)

# engine that really call tools and manage the conversation
AGENT = AgentExecutor(agent=agent_runnable, tools=tools, verbose=True, return_intermediate_steps=True)
