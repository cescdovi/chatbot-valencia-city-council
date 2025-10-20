from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import AIMessage, HumanMessage
from langchain.load import dumps, loads

prompt = ChatPromptTemplate.from_messages([
    ("system", "Eres útil."),
    MessagesPlaceholder("history"),
    ("human", "{input}")
])
print(type(prompt).__name__)
