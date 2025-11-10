import json
from langchain.messages import AIMessage,ToolMessage
from api_backend.src.agent import AGENT

def try_parse_json(text):
    """Devuelve JSON si es válido, o None si no lo es."""
    try:
        return json.loads(text)
    except Exception:
        return None
    
for chunk in AGENT.stream(  
    {"messages": [{"role": "user", "content": "Cual es la legislacion relacionada con los certificados IRPF?"}]},
    stream_mode="updates",
):
    for step, data in chunk.items():
        #print(f"-- STEP: {step}---")
        #print(f"--  DATA: {data}\n")

        last_block = data["messages"][-1].content_blocks  # propiedad generica para acceder a las llamadas a tools o respuestas
        print(f"--  CONTENT BLOCK: {last_block}\n\n")

        if isinstance(data["messages"][-1], AIMessage):

            #model action
            if (last_block[-1].get("type", {}) and last_block[-1].get("name")) is not None:
                print("MODEL ACTION")
                print("---TIPO---",last_block[-1].get("type"))
                print("---NOMBRE---",last_block[-1].get("name"))

                qry = last_block[-1].get("args").get("query") if last_block[-1].get("args") else None
                print("---QUERY---",qry)

            #model final response
            elif (last_block[-1].get("type", {}) and last_block[-1].get("text", {})) is not None:
                print("MODEL FINAL RESPONSE")
                print("---FINAL RESPONSE TYPE ---",last_block[-1].get("type"))
                print("---FINAL RESPONSE TEXT ---",last_block[-1].get("text"))

            else:
                continue
        
        #tool responses           
        if isinstance(data["messages"][-1], ToolMessage):
            print("TOOL RESPONSE")

            # tool neo4j_query response
            if (last_block[-1].get("type", {}) and last_block[-1].get("text")) is not None:
                print("TOOL NEO4J")
                print("---TIPO---",last_block[-1].get("type"))
                print("---NOMBRE---",last_block[-1].get("text"))
            
            # tool search_law response
            elif try_parse_json(last_block[-1].get("text")) is not None:
                print("TOOL SEARCH LAW")
                text = last_block[-1].get("text")
                search_results = json.loads(text)
                for r in search_results.get("results", []):
                    print(f"      URL   : {r.get('url')}")
                    print(f"      TITLE : {r.get('title')}")
                    print(f"      CONTENT: {r.get('content')}\n")

            else:
                continue

        print("\n\n")

