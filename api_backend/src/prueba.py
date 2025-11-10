import json
from typing import List, Any, Dict, Optional

from fastapi import FastAPI
from pydantic import BaseModel

#  Ajusta estos imports a tu proyecto real
from langchain_core.messages import AIMessage, ToolMessage
# from my_agent_module import AGENT

app = FastAPI()


# --------- MODELOS DE ENTRADA (IGUAL QUE EN TU /chat) ---------

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]


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
    for step, data in chunk.items():
        msg = data["messages"][-1]
        last_block = data["messages"][-1].content_blocks

        # --------- Eventos de modelo (AIMessage) ---------
        if isinstance(msg, AIMessage):

            # MODEL ACTION (llamada a tool)
            if (last_block.get("type") and last_block.get("name")) is not None:
                #qry = last_block.get("args", {}).get("query")
                qry = last_block[-1].get("args").get("query") if last_block[-1].get("args") else None

                yield {
                    "event_type": "model_action",
                    "type": last_block.get("type"),           
                    "tool_name": last_block.get("name"),
                    "query": qry,
                }

            # MODEL FINAL RESPONSE (texto final)
            elif (last_block.get("type") and last_block.get("text")) is not None:
                yield {
                    "event_type": "model_final_response",
                    "type": last_block.get("type"),
                    "text": last_block.get("text"),
                }

            continue

        # --------- Eventos de herramientas (ToolMessage) ---------
        if isinstance(msg, ToolMessage):
            base_event: Dict[str, Any] = {
                "event_type": "tool_response",
                "type": last_block.get("type"),
                "tool_query": last_block.get("text"),
            }

            # TOOL NEO4J (tiene name + args)
            if (last_block.get("type") and last_block.get("text")) is not None:
                yield {
                    **base_event,
                    "event_type": "tool_neo4j",
                }
                continue

            # TOOL SEARCH LAW (texto JSON parseable)
            parsed = try_parse_json(last_block.get("text") or "")
            if parsed is not None:
                results = parsed.get("results", [])

                # Evento con todos los resultados
                for r in results:
                    yield {
                        **base_event,
                        "event_type": "tool_search_law",
                        "url": r.get("url"),
                        "title": r.get("title"),
                        "content": r.get("content"),
                    }

                continue

            # Tool genérica
            yield base_event
