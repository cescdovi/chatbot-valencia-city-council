import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

from dotenv import load_dotenv
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

@app.post("/chat")
async def chat(request: ChatRequest):
    """
    CARACTERÍSTICAS DEL ENDPOINT:
    - Asincrono: conforme el agente va generando tokens de respuesta, se consumen y se envian al frontend
    - Respuestas del endpoint /chat en formato JSONL, no JSON: cada vez que se genera un evento (token, fuente, fin de respuesta)
      se envia una LINE JSON. Esto permite al frontend procesar la respuesta en tiempo real.
    """
    try:
        async def response_generator():
            user_input = request[-1].content
            try: 
                async for ev in AGENT.astream_events({"input": user_input}, version="v1"):
                    logging.info(f"Event generated: {ev}")
                    yield json.dumps(ev) + "\n"
            except Exception as e:
                logging.error(f"Error during agent response generation: {e}")
                yield json.dumps({"error": str(e)}) + "\n"
            
        return StreamingResponse(
            response_generator(),
            media_type="text/plain; charset=utf-8",
            headers={
                # Sugerencias para evitar buffering en proxies/CDN
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )


    except Exception as e:
        logger.error(f"Error in /chat endpoint: {e}")
        raise Exception(f"Error processing chat request: {e}")
    

if __name__ == "__main__":

    import uvicorn
    # uvicorn is the ASGI server that will run the FastAPI app to be accessible by HTTP
    uvicorn.run(
        "api_backend.src.app:app", #route to the app instance
        host="0.0.0.0",            #listen on all interfaces (independent of network interface IP)
        port=settings.BACKEND_PORT #port to listen on
    )