from __future__ import annotations
import os, json, shutil, subprocess
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from pathlib import Path
from contextlib import AsyncExitStack

from .logging_mcp import JsonlLogger
from .config import LOG_PATH, WORKSPACE_DIR

@dataclass
class ServerConfig:
    id: str
    command: str
    args: List[str]
    env: Dict[str,str]

class MCPClientManager:
    def __init__(self, servers: List[ServerConfig]):
        self.servers_cfg = servers
        self.logger = JsonlLogger(LOG_PATH)
        self._sessions: Dict[str, Any] = {}
        self._sdk = None
        self._exit_stack: Optional[AsyncExitStack] = None
        self._sessions: Dict[str, Any] = {}
        self._sdk = None
        self._exit_stack: Optional[AsyncExitStack] = None

    async def start(self) -> None:
        try:
            from mcp import ClientSession, StdioServerParameters  # type: ignore
            from mcp.client.stdio import stdio_client  # type: ignore
            self._sdk = {"ClientSession": ClientSession, "StdioServerParameters": StdioServerParameters, "stdio_client": stdio_client}
        except Exception as e:
            raise RuntimeError("El SDK de MCP no está disponible. Instala la librería `mcp` y sus dependencias.") from e

        self._exit_stack = AsyncExitStack()
        await self._exit_stack.__aenter__()

        for s in self.servers_cfg:
            try:
                params = self._sdk["StdioServerParameters"](command=s.command, args=s.args, env={**os.environ, **s.env} if s.env else None)
                stdio, write = await self._exit_stack.enter_async_context(self._sdk["stdio_client"](params))
                session = await self._exit_stack.enter_async_context(self._sdk["ClientSession"](stdio, write))
                await session.initialize()
                self._sessions[s.id] = session
                self.logger.write({"event":"initialize","server":s.id})
            except Exception as e:
                self.logger.write({"event":"initialize_error","server":s.id,"error":str(e)})

    async def close(self) -> None:
        if self._exit_stack is not None:
            try:
                await self._exit_stack.aclose()
            except Exception:
                pass

    async def list_tools(self, server_id: Optional[str]=None) -> Dict[str, List[Dict[str, Any]]]:
        out: Dict[str, List[Dict[str, Any]]] = {}
        if True:
            targets = [(server_id, self._sessions.get(server_id))] if server_id else self._sessions.items()
            for sid, session in targets:
                if not session:
                    continue
                try:
                    response = await session.list_tools()
                    tools = getattr(response, "tools", []) or []
                    arr = []
                    for t in tools:
                        name = getattr(t, "name", None)
                        desc = getattr(t, "description", None)
                        schema = getattr(t, "input_schema", None) or getattr(t, "inputSchema", None)
                        try:
                            schema = json.loads(json.dumps(schema, default=lambda o: getattr(o, "__dict__", str(o))))
                        except Exception:
                            pass
                        arr.append({"name": name, "description": desc, "input_schema": schema})
                    out[sid] = arr
                    self.logger.write({"event":"tools/list","server":sid,"tools_count":len(arr)})
                except Exception as e:
                    self.logger.write({"event":"tools/list_error","server":sid,"error":str(e)})
        return out

    async def get_schema(self, server_id: str, tool_name: str) -> Dict[str, Any]:
        tools = await self.list_tools(server_id)
        for t in tools.get(server_id, []):
            if t.get("name") == tool_name:
                return {"name": tool_name, "input_schema": t.get("input_schema"), "description": t.get("description")}
        raise RuntimeError(f"Herramienta no encontrada: {server_id}:{tool_name}")

    async def call_tool(self, server_id: str, tool_name: str, args: Dict[str, Any]) -> Any:
        if True:
            session = self._sessions.get(server_id)
            if not session:
                raise RuntimeError(f"Servidor no conectado: {server_id}")
            try:
                self.logger.write({"event":"tools/call","server":server_id,"tool":tool_name,"args":args})
                result = await session.call_tool(tool_name, args or {})
                try:
                    payload = getattr(result, "content", None)
                    res = {"content": json.loads(json.dumps(payload, default=lambda o: getattr(o, "__dict__", str(o))))}
                except Exception:
                    res = json.loads(json.dumps(result, default=lambda o: getattr(o, "__dict__", str(o))))
                self.logger.write({"event":"tools/response","server":server_id,"tool":tool_name,"result":res})
                return res
            except Exception as e:
                self.logger.write({"event":"tools/error","server":server_id,"tool":tool_name,"error":str(e)})
                raise
    async def run_inciso4_scenario(self) -> List[str]:
        steps: List[str] = []
        WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
        await self.call_tool("fs","mkdir",{"path": str(WORKSPACE_DIR), "exist_ok": True})
        steps.append(f"mkdir {WORKSPACE_DIR}")
        readme_path = WORKSPACE_DIR / "README.md"
        content = "# Proyecto MCP — Inciso 4\n\nEste README fue creado desde el host por una tool FS.\n"
        await self.call_tool("fs","write_file",{"path": str(readme_path), "content": content})
        steps.append("write README.md")
        target_git = "github" if "github" in self._sessions else "git"
        try:
            await self.call_tool(target_git,"git_init",{})
            await self.call_tool(target_git,"git_add_all",{})
            await self.call_tool(target_git,"git_commit",{"message":"chore: add README for inciso 4"})
            steps.append(f"git init/add/commit via {target_git}")
        except Exception as e:
            steps.append(f"[ADVERTENCIA] Git no disponible ({e}) — omitiendo paso git")
        return steps
