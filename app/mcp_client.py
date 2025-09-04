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
        self.mode = "sdk"
        self._sessions: Dict[str, Any] = {}
        self._sdk = None
        self._exit_stack: Optional[AsyncExitStack] = None

    async def start(self) -> None:
        try:
            from mcp import ClientSession, StdioServerParameters  # type: ignore
            from mcp.client.stdio import stdio_client  # type: ignore
            self._sdk = {"ClientSession": ClientSession, "StdioServerParameters": StdioServerParameters, "stdio_client": stdio_client}
        except Exception as e:
            self.mode = "fallback"
            self.logger.write({"event": "sdk_unavailable", "error": str(e)})
            return

        self._exit_stack = AsyncExitStack()
        await self._exit_stack.__aenter__()

        for s in self.servers_cfg:
            try:
                params = self._sdk["StdioServerParameters"](command=s.command, args=s.args, env={**os.environ, **s.env} if s.env else None)
                stdio, write = await self._exit_stack.enter_async_context(self._sdk["stdio_client"](params))
                session = await self._exit_stack.enter_async_context(self._sdk["ClientSession"](stdio, write))
                await session.initialize()
                self._sessions[s.id] = session
                self.logger.write({"event":"initialize","server":s.id,"mode":self.mode})
            except Exception as e:
                self.logger.write({"event":"initialize_error","server":s.id,"error":str(e)})

    async def close(self) -> None:
        if self.mode == "sdk" and self._exit_stack is not None:
            try:
                await self._exit_stack.aclose()
            except Exception:
                pass

    async def list_tools(self, server_id: Optional[str]=None) -> Dict[str, List[Dict[str, Any]]]:
        out: Dict[str, List[Dict[str, Any]]] = {}
        if self.mode == "sdk":
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
        else:
            out["fs"] = [
                {"name":"write_file","description":"Escribe archivo (path, content)","input_schema":{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"]}},
                {"name":"read_file","description":"Lee archivo (path)","input_schema":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}},
                {"name":"mkdir","description":"Crea carpeta (path, exist_ok?)","input_schema":{"type":"object","properties":{"path":{"type":"string"},"exist_ok":{"type":"boolean"}},"required":["path"]}},
            ]
            out["git"] = [
                {"name":"git_init","description":"Inicializa repo git en WORKSPACE_DIR","input_schema":{"type":"object","properties":{},"required":[]}},
                {"name":"git_add_all","description":"git add -A","input_schema":{"type":"object","properties":{},"required":[]}},
                {"name":"git_commit","description":"git commit -m <msg>","input_schema":{"type":"object","properties":{"message":{"type":"string"}},"required":["message"]}},
            ]
            self.logger.write({"event":"tools/list","server":"fallback","tools_count":len(out['fs'])+len(out['git'])})
        return out

    async def get_schema(self, server_id: str, tool_name: str) -> Dict[str, Any]:
        tools = await self.list_tools(server_id)
        for t in tools.get(server_id, []):
            if t.get("name") == tool_name:
                return {"name": tool_name, "input_schema": t.get("input_schema"), "description": t.get("description")}
        raise RuntimeError(f"Herramienta no encontrada: {server_id}:{tool_name}")

    async def call_tool(self, server_id: str, tool_name: str, args: Dict[str, Any]) -> Any:
        if self.mode == "sdk":
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

        # ---- Fallback local ----
        self.logger.write({"event":"tools/call","server":f"fallback:{server_id}","tool":tool_name,"args":args})
        if server_id in ("fs","filesystem"):
            if "path" not in args:
                raise RuntimeError("Falta 'path'")
            path = Path(args["path"]).resolve()
            if tool_name == "write_file":
                if path.is_dir():
                    raise RuntimeError("'path' debe ser un archivo, no un directorio")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(args.get("content",""), encoding="utf-8")
                res = {"ok": True, "path": str(path)}
            elif tool_name == "read_file":
                if path.is_dir():
                    raise RuntimeError("'path' debe ser un archivo, no un directorio")
                res = {"ok": True, "path": str(path), "content": path.read_text(encoding="utf-8")}
            elif tool_name == "mkdir":
                exist_ok = bool(args.get("exist_ok", True))
                path.mkdir(parents=True, exist_ok=exist_ok)
                res = {"ok": True, "path": str(path)}
            else:
                raise RuntimeError(f"Tool no soportada en fallback FS: {tool_name}")
        elif server_id in ("git","github","gitlocal"):
            cwd = WORKSPACE_DIR
            cwd.mkdir(parents=True, exist_ok=True)
            if tool_name == "git_init":
                if not shutil.which("git"):
                    raise RuntimeError("git no encontrado en PATH")
                subprocess.check_call(["git","init"], cwd=str(cwd))
                res = {"ok": True, "cwd": str(cwd)}
            elif tool_name == "git_add_all":
                subprocess.check_call(["git","add","-A"], cwd=str(cwd))
                res = {"ok": True}
            elif tool_name == "git_commit":
                msg = args.get("message","Initial commit")
                try:
                    subprocess.check_call(["git","-c","user.name=Student","-c","user.email=student@example.com","commit","-m",msg], cwd=str(cwd))
                except subprocess.CalledProcessError as e:
                    raise RuntimeError("git commit falló (¿hay cambios nuevos?)") from e
                res = {"ok": True, "message": msg}
            else:
                raise RuntimeError(f"Tool no soportada en fallback Git: {tool_name}")
        else:
            raise RuntimeError(f"Servidor fallback desconocido: {server_id}")

        self.logger.write({"event":"tools/response","server":f"fallback:{server_id}","tool":tool_name,"result":res})
        return res

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
