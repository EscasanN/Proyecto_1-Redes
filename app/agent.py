
from __future__ import annotations
import json, re, asyncio
from typing import Any, Dict, List, Optional, Tuple

from .mcp_client import MCPClientManager

CALL_RE = re.compile(r"^###\s*CALL\s*(\{.*\})\s*###\s*$", re.DOTALL)
FINAL_RE = re.compile(r"^###\s*FINAL\s*(\{.*\})\s*###\s*$", re.DOTALL)

SYSTEM_INSTRUCTION = """\
Eres un agente que puede usar herramientas MCP para cumplir objetivos del usuario.
Dispones de estos servidores y herramientas (formato JSON):

{catalog}

Cómo trabajar:
1) Piensa de manera breve qué hacer.
2) Si NECESITAS una herramienta, responde **únicamente** una línea:
### CALL {{"server_id":"<sid>","name":"<tool_name>","arguments":{{ ... JSON ... }}}} ###
3) Cuando ya tengas la respuesta final para el usuario, responde **únicamente**:
### FINAL {{"text":"...respuesta para el usuario..."}} ###

Reglas IMPORTANTES:
- Los argumentos deben ser JSON VÁLIDO y cumplir el esquema de la herramienta.
- No inventes servidores o herramientas.
- Si recibes un error, intenta corregir parámetros y vuelve a llamar la herramienta.
- No repitas el catálogo en tus respuestas.
- Si el usuario te pide crear un README y hacer commit, usa fs.write_file y git.* en secuencia.
"""

class ToolUseAgent:
    def __init__(self, llm_client, mcp_mgr: MCPClientManager, max_steps: int = 8):
        self.llm = llm_client   # expects methods: start(system_prompt), ask(text)
        self.mcp = mcp_mgr
        self.max_steps = max_steps
        self._started = False

    async def _build_catalog(self) -> str:
        tools = await self.mcp.list_tools()
        # Render a compact JSON with schemas
        display = {}
        for sid, arr in tools.items():
            display[sid] = [
                {
                    "name": t.get("name"),
                    "description": t.get("description"),
                    "input_schema": t.get("input_schema"),
                } for t in arr
            ]
        return json.dumps(display, ensure_ascii=False, indent=2)

    async def start(self):
        if self._started: 
            return
        catalog = await self._build_catalog()
        system = SYSTEM_INSTRUCTION.format(catalog=catalog)
        self.llm.start(system_instruction=system)
        self._started = True

    async def run(self, user_text: str) -> Dict[str, Any]:
        """Runs an agentic loop until FINAL. Returns {'final': str, 'trace': [...]}"""
        await self.start()
        trace: List[Dict[str, Any]] = []
        # Send the user query
        msg = f"Usuario: {user_text}\nRecuerda usar CALL/FINAL."
        reply = self.llm.ask(msg)
        for step in range(self.max_steps):
            # Check for FINAL
            m_final = FINAL_RE.match(reply.strip())
            if m_final:
                try:
                    payload = json.loads(m_final.group(1))
                except json.JSONDecodeError:
                    payload = {"text": reply}
                return {"final": payload.get("text", reply), "trace": trace}

            # Otherwise expect CALL
            m_call = CALL_RE.match(reply.strip())
            if not m_call:
                # Ask model to follow the format
                reply = self.llm.ask("El formato no es válido. Debes responder con ### CALL {...} ### o ### FINAL {...} ### únicamente. Reintenta.")
                continue

            try:
                call_payload = json.loads(m_call.group(1))
                sid = call_payload["server_id"]
                name = call_payload["name"]
                args = call_payload.get("arguments", {}) or {}
            except Exception as e:
                reply = self.llm.ask(f"El JSON del CALL no es válido ({e}). Reintentemos con el formato indicado.")
                continue

            # Execute the tool via MCP
            try:
                result = await self.mcp.call_tool(sid, name, args)
                obs = {"server_id": sid, "name": name, "args": args, "result": result}
                trace.append({"type":"call", **obs})
                # Feed observation
                reply = self.llm.ask(f"OBSERVACIÓN:\n{json.dumps(result, ensure_ascii=False)}\nAhora continúa. Recuerda usar CALL/FINAL.")
            except Exception as e:
                trace.append({"type":"error", "server_id": sid, "name": name, "args": args, "error": str(e)})
                reply = self.llm.ask(f"ERROR al ejecutar la herramienta {sid}:{name} — {e}. Corrige los parámetros o elige otra herramienta y reintenta con CALL.")
        # If we exit loop without FINAL
        return {"final": "No logré completar la tarea dentro del límite de pasos.", "trace": trace}
