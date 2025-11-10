import json
import logging

from typing import Dict, Optional

from langchain.messages import AIMessage,ToolMessage

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from config.common_settings import settings
from api_backend.src.agent import AGENT
from api_backend.src.pydantic_models import ChatRequest
#logging 
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

#init the app
app = FastAPI(title="Valencia City Council Chatbot API", version="1.0.0")

# Set up CORS middleware
origins = [settings.FRONTEND_URL]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


#endpoints
@app.get("/")
async def root():
    return {"message": "The chat app is running"}

@app.get("/health")
def health_check():
    logger.info("Health check endpoint called")
    return {"status": "ok"}

def try_parse_json(text: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(text)
    except Exception:
        return None


def build_events_from_chunk(chunk: Dict[str, Any]):
    """
    Traducimos los chunks de AGENT.stream en 'eventos' de alto nivel.
    Generador síncrono: yield dict por cada evento detectado.
    """
    #print("Received chunk:", chunk)  # Debug: print the entire chunk
    for step, data in chunk.items():
        msg = data["messages"][-1]
        last_block = data["messages"][-1].content_blocks

        # --------- Eventos de modelo (AIMessage) ---------
        if isinstance(msg, AIMessage):

            # MODEL ACTION (llamada a tool)
            if (last_block[-1].get("type") and last_block[-1].get("name")) is not None:

                #qry = last_block.get("args", {}).get("query")
                qry = last_block[-1].get("args").get("query") if last_block[-1].get("args") else None
                logging.info(f"---MODEL ACTION--- tool={last_block[-1].get('name')}, query={qry}")

                yield {
                    "event_type": "model_action",
                    "type": last_block[-1].get("type"),           
                    "tool_name": last_block[-1].get("name"),
                    "query": qry,
                }

            # MODEL FINAL RESPONSE (texto final)
            elif (last_block[-1].get("type") and last_block[-1].get("text")) is not None:

                logging.info(f"---MODEL FINAL RESPONSE--- tool={last_block[-1].get('name')}, text={last_block[-1].get('text')}")
                yield {
                    "event_type": "model_final_response",
                    "type": last_block[-1].get("type"),
                    "text": last_block[-1].get("text"),
                }

            continue

        # --------- Eventos de herramientas (ToolMessage) ---------
        if isinstance(msg, ToolMessage):
            base_event: Dict[str, Any] = {
                "event_type": "tool_response",
                "type": last_block[-1].get("type"),
                #"tool_query": last_block[-1].get("text"),
            }
            parsed_json = try_parse_json(last_block[-1].get("text"))

            # TOOL NEO4J (tiene name + args)
            if parsed_json is not None and "results" not in parsed_json:

                logging.info(f"---TOOL NEO4J RESPONSE--- type={last_block[-1].get('type')}, tool_query={last_block[-1].get('text')}")
                yield {
                    **base_event,
                    "event_type": "tool_neo4j",
                }
                continue

            # TOOL SEARCH LAW (texto JSON parseable)
            parsed_json = try_parse_json(last_block[-1].get("text"))
            if parsed_json is not None and "results" in parsed_json:
                logging.info("---TOOL SEARCH LAW RESPONSE DETECTED---")
                search_results = parsed_json
                for r in search_results.get("results", []):
                    logging.info(f"---TOOL SEARCH LAW RESPONSE--- type={last_block[-1].get('type')}, url={r.get('url')}, title={r.get('title')}, content={r.get('content')}")
                    yield {
                        **base_event,
                        "event_type": "tool_search_law",
                        "url": r.get("url"),
                        "title": r.get("title"),
                        "content": r.get("content"),
                    }

                continue

            else: 
                continue

            # Tool genérica
            #yield base_event


@app.post("/chat")
async def chat(request: ChatRequest):
    try:
        agent_input = {
            "messages": [
                {"role": msg.role, "content": msg.content}
                for msg in request.messages
            ]
        }
        print(agent_input)
        async def response_generator():
            #user_input = request.messages[-1].content
            try:
                logging.info(f"---RECEIVED USER INPUT: {agent_input}---")

                async for chunk in AGENT.astream(agent_input, stream_mode="updates"):
                    for event in build_events_from_chunk(chunk):
                        print("\n\n")
                        yield json.dumps(event, ensure_ascii=False) + "\n"

        
            except Exception as e:
                logging.error(f"Error during agent response generation: {e}")
                yield json.dumps({"error": str(e)}) + "\n"
                                      
        return StreamingResponse(
            response_generator(),
            media_type="text/plain; charset=utf-8",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception as e:
        logging.error(f"Error in /chat endpoint: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

if __name__ == "__main__":

    import uvicorn
    # uvicorn is the ASGI server that will run the FastAPI app to be accessible by HTTP
    uvicorn.run(
        "api_backend.src.app:app", #route to the app instance
        host="0.0.0.0",            #listen on all interfaces (independent of network interface IP)
        port=settings.BACKEND_PORT #port to listen on
    )