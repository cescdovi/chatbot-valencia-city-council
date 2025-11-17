import os
import json
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import httpx
import streamlit as st

from config.common_settings import settings
# ──────────────────────────────────────────────────────────────────────────────
# Config & logging
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Chatbot using Streamlit, FastAPI and Langchain", layout="wide")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _normalize_base(url: Optional[str]) -> str:
    base = (url or "http://backend:8000").strip()
    # elimina slash final para construir rutas con f"{base}/path"
    if base.endswith("/"):
        base = base[:-1]
    return base

API_BASE = _normalize_base(settings.CONT_BACKEND_URL)

# Timeouts
HEALTH_CHECK_TIMEOUT = 5.0
REQUEST_TIMEOUT = httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=5.0)

# ──────────────────────────────────────────────────────────────────────────────
# Estado de hilos (threads)
# ──────────────────────────────────────────────────────────────────────────────
def _ensure_threads_state():
    if "threads" not in st.session_state:
        st.session_state.threads = {}
    if "active_thread_id" not in st.session_state:
        tid = _new_thread_id()
        st.session_state.threads[tid] = _empty_thread()
        st.session_state.active_thread_id = tid

def _new_thread_id():
    return str(uuid.uuid4())

def _empty_thread(title: str = "Nueva conversación"):
    return {
        "title": title,
        "created": datetime.utcnow().isoformat(),
        "messages": [],  # {"role":"user"/"assistant","content": str, "context_md": Optional[str]}
    }

def get_active_messages():
    tid = st.session_state.active_thread_id
    return st.session_state.threads[tid]["messages"]

def set_active_messages(messages):
    tid = st.session_state.active_thread_id
    st.session_state.threads[tid]["messages"] = messages

def thread_autotitle(messages):
    first_user = next((m for m in messages if m["role"] == "user"), None)
    if not first_user:
        return "Nueva conversación"
    txt = first_user["content"].strip().replace("\n", " ")
    return (txt[:40] + "…") if len(txt) > 40 else txt

_ensure_threads_state()

# ──────────────────────────────────────────────────────────────────────────────
# Sidebar (selector de hilos + health)
# ──────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.subheader("💬 Conversaciones")

    c_new, c_health = st.columns([1, 1])
    with c_new:
        if st.button("➕ Nuevo hilo", use_container_width=True):
            new_id = _new_thread_id()
            st.session_state.threads[new_id] = _empty_thread()
            st.session_state.active_thread_id = new_id
            st.rerun()

    with c_health:
        health = "❓"
        tip = f"Base: {API_BASE}"
        try:
            with httpx.Client(timeout=HEALTH_CHECK_TIMEOUT, http2=True) as c:
                r = c.get(f"{API_BASE}/health")
                health = "🟢" if r.status_code == 200 else "🟠"
                tip = f"{tip}\nStatus: {r.status_code}"
        except Exception as e:
            health = "🔴"
            tip = f"{tip}\nError: {e}"
        st.button(f"{health} Backend", help=tip, use_container_width=True, disabled=True)

    # Selector de hilos
    ids = list(st.session_state.threads.keys())
    labels = []
    for tid in ids:
        msgs = st.session_state.threads[tid]["messages"]
        title = st.session_state.threads[tid]["title"]
        auto = thread_autotitle(msgs)
        labels.append(f"🧵 {auto if msgs else title}")

    active_id = st.session_state.active_thread_id
    idx_active = ids.index(active_id)

    chosen = st.radio(
        "Hilos",
        options=ids,
        index=idx_active,
        format_func=lambda tid: labels[ids.index(tid)],
        label_visibility="collapsed",
    )
    if chosen != active_id:
        st.session_state.active_thread_id = chosen
        st.rerun()

    # Opciones del hilo activo
    with st.popover("⋯ Opciones del hilo"):
        cur = st.session_state.threads[st.session_state.active_thread_id]
        new_title = st.text_input("Título del hilo", value=cur["title"])
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("Guardar", use_container_width=True):
                cur["title"] = new_title.strip() or cur["title"]
                st.rerun()
        with c2:
            if st.button("Renombrar automático", use_container_width=True):
                cur["title"] = thread_autotitle(cur["messages"])
                st.rerun()
        with c3:
            if st.button("🗑️ Eliminar hilo", use_container_width=True):
                if len(st.session_state.threads) > 1:
                    del st.session_state.threads[st.session_state.active_thread_id]
                    st.session_state.active_thread_id = next(iter(st.session_state.threads))
                    st.rerun()
                else:
                    st.warning("No puedes eliminar el único hilo.")

# ──────────────────────────────────────────────────────────────────────────────
# Encabezado
# ──────────────────────────────────────────────────────────────────────────────
st.title("Chatbot using Streamlit, FastAPI and Langchain")
st.header("About")
st.markdown(
    """
This chatbot uses info from https://sede.valencia.es/sede/registro/indexM.xhtml?lang=1&m=HA to answer your questions
"""
)

# ──────────────────────────────────────────────────────────────────────────────
# Render historial del hilo activo
# ──────────────────────────────────────────────────────────────────────────────
active_messages = get_active_messages()
for i, m in enumerate(active_messages):
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if m.get("context_md") and m["role"] == "assistant":
            with st.expander(f"🔎 Contexto de la respuesta · {i}", expanded=False):
                st.markdown(m["context_md"])

# ──────────────────────────────────────────────────────────────────────────────
# Helpers de render
# ──────────────────────────────────────────────────────────────────────────────
def render_context_block(tools_used: Dict[str, int], sources: List[Dict], fragments: Optional[List[Dict]] = None) -> str:
    fragments = fragments or []
    lines = []
    lines.append("\n---\n")
    lines.append("### 🧰 Herramientas usadas\n")
    if tools_used:
        for name, cnt in tools_used.items():
            lines.append(f"- {name} × {cnt}")
    else:
        lines.append("- (ninguna)")

    lines.append("\n### 🔎 Fuentes consultadas\n")
    if sources:
        for i, s in enumerate(sources, 1):
            title = s.get("title") or s.get("url") or "Fuente"
            url = s.get("url")
            if url:
                lines.append(f"{i}. [{title}]({url})")
            else:
                lines.append(f"{i}. {title}")
    else:
        lines.append("- (no se obtuvieron fuentes)")

    if fragments:
        lines.append("\n### 📄 Fragmentos utilizados (RAG)\n")
        for i, fr in enumerate(fragments[:5], 1):
            t = fr.get("title", f"Documento {i}")
            sn = fr.get("snippet", "")
            lines.append(f"**{t}**\n\n{sn}…\n")

    return "\n".join(lines)

# ──────────────────────────────────────────────────────────────────────────────
# Streaming al backend y render
# ──────────────────────────────────────────────────────────────────────────────
def stream_and_render(messages: List[Dict[str, str]]):
    """
    Envía mensajes al backend y renderiza:
      - event_type = "model_final_response"  → texto acumulado
      - event_type = "model_action" / "tool_neo4j" / "tool_search_law" → contexto (herramientas, fuentes)
    Devuelve (texto_final, context_dict|None)
    """
    text_placeholder = st.empty()
    final_text = ""

    # acumuladores de contexto (lo que luego usará render_context_block)
    tools_used: Dict[str, int] = {}
    sources: List[Dict] = []
    fragments: List[Dict] = []

    context_dict = None

    with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True, http2=False) as client:
        with client.stream(
            "POST",
            f"{API_BASE}/chat",
            json={"messages": messages},
            headers={"Accept": "text/plain"},
        ) as r:
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                try:
                    e.response.read()
                    body = e.response.text[:2000]
                except Exception:
                    body = "<sin cuerpo>"
                err = f"Error: HTTP {e.response.status_code} - {body}"
                text_placeholder.markdown(err)
                return err, None

            for line in r.iter_lines():
                if not line:
                    continue

                # cada línea debería ser un JSON
                try:
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    # fallback por si llega texto plano
                    final_text += line
                    text_placeholder.markdown(final_text)
                    continue

                # ---- manejo de errores enviados por el backend ----
                if evt.get("event_type") == "error" or "error" in evt:
                    msg = evt.get("message") or evt.get("error") or "Error desconocido"
                    final_text += f"\n\n⚠️ {msg}"
                    text_placeholder.markdown(final_text)
                    continue

                evt_type = evt.get("event_type")

                # ---- texto final del modelo ----
                if evt_type == "model_final_response":
                    delta = evt.get("text", "")
                    if delta:
                        final_text += delta
                        text_placeholder.markdown(final_text)
                    continue

                # ---- acción de modelo: llamada a herramienta ----
                if evt_type == "model_action":
                    tool_name = evt.get("tool_name") or "desconocida"
                    tools_used[tool_name] = tools_used.get(tool_name, 0) + 1
                    continue

                # ---- respuesta de herramienta NEO4J ----
                if evt_type == "tool_neo4j":
                    tools_used["neo4j"] = tools_used.get("neo4j", 0) + 1
                    src = {
                        "url": evt.get("url"),
                        "title": evt.get("title"),
                        "content": evt.get("content"),
                    }
                    continue

                # ---- respuesta de herramienta de búsqueda de leyes ----
                if evt_type == "tool_search_law":
                    tools_used["search_law"] = tools_used.get("search_law", 0) + 1
                    src = {
                        "url": evt.get("url"),
                        "title": evt.get("title"),
                        "content": evt.get("content"),
                    }
                    sources.append(src)

                    # opcional: también lo consideramos fragmento de RAG
                    fragments.append(
                        {
                            "title": evt.get("title"),
                            "snippet": evt.get("content", "")[:400],
                        }
                    )
                    continue

            # construir contexto (si hay algo)
            if tools_used or sources or fragments:
                context_dict = {
                    "tools_used": tools_used,
                    "sources": sources,
                    "fragments": fragments,
                }

    return final_text, context_dict


# ──────────────────────────────────────────────────────────────────────────────
# Input del usuario
# ──────────────────────────────────────────────────────────────────────────────
if prompt := st.chat_input(placeholder="Escribe tu mensaje aquí"):
    # Usuario
    with st.chat_message("user"):
        st.markdown(prompt)
    active_messages.append({"role": "user", "content": prompt})
    set_active_messages(active_messages)

    # Asistente (streaming)
    with st.chat_message("assistant"):
        assistant_text, context = stream_and_render(active_messages)

        ctx_md = None
        if context:
            ctx_md = render_context_block(
                tools_used=context.get("tools_used", {}),
                sources=context.get("sources", []),
                fragments=context.get("fragments", []),
            )
            with st.expander(f"🔎 Contexto de la respuesta · {len(active_messages)}", expanded=False):
                st.markdown(ctx_md)

    # Guardar respuesta + contexto como un solo mensaje del asistente
    active_messages.append({
        "role": "assistant",
        "content": assistant_text,
        "context_md": ctx_md,
    })
    set_active_messages(active_messages)