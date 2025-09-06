from __future__ import annotations
import asyncio, json
from typing import Dict, Any, List
from rich.console import Console
from rich.prompt import Prompt

from .config import SERVERS_YAML, SERVERS_EXAMPLE, WORKSPACE_DIR, LOG_PATH
from .llm_client import LLMClient
from .mcp_client import MCPClientManager, ServerConfig
from .agent import ToolUseAgent

console = Console()

def load_servers() -> List[ServerConfig]:
    import yaml
    path = SERVERS_YAML if SERVERS_YAML.exists() else SERVERS_EXAMPLE
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    servers = []
    for s in data.get("servers", []):
        servers.append(ServerConfig(
            id=s["id"],
            command=s["command"],
            args=s.get("args", []),
            env=s.get("env", {}) or {}
        ))
    return servers

async def run_cli():
    console.print(f"[bold green]MCP Host CLI (Gemini)[/] — logs: {LOG_PATH}")
    console.print(f"Workspace: {WORKSPACE_DIR}")
    try:
        llm = LLMClient()
    except Exception as e:
        console.print(f"[yellow]Advertencia:[/] LLM no inicializado — {e}")
        llm = None

    servers = load_servers()
    mcp_mgr = MCPClientManager(servers)
    await mcp_mgr.start()
    agent = ToolUseAgent(llm, mcp_mgr, max_steps=25)
    console.print(f"[cyan]MCP conectado.[/] Usa :tools para listar herramientas.")

    console.print("\nEscribe texto para chatear con el LLM (con uso de herramientas). Comandos disponibles:")
    console.print(":help — ayuda")
    console.print(":tools — listar herramientas conectadas")
    console.print(":call <server> <tool> {json} — invocar manualmente")
    console.print(":scenario — demo inciso 4 (fs + git)")
    while True:
        try:
            cmd = Prompt.ask("[bold magenta](mcp) ›[/]")
        except (EOFError, KeyboardInterrupt):
            console.print("\nSaliendo...")
            break

        if not cmd.strip():
            continue

        if cmd.strip() in (":q", ":quit", ":exit"):
            break

        if cmd.strip() in (":help", ":h"):
            console.print("""
[bold]:help[/] — esta ayuda
[bold]:servers[/] — lista servidores conectados
[bold]:tools [server][/] — lista tools (todos o por servidor)
[bold]:schema <server> <tool>[/] — muestra el JSON Schema de entrada
[bold]:call <server> <tool> <json-args>[/] — invoca una tool
[bold]:scenario[/] — ejecuta el flujo del inciso 4 (FS + Git)
[bold]:log[/] — muestra ruta del log
[bold]:q[/] — salir
            """.strip())
            continue

        if cmd.strip() == ":log":
            console.print(f"Log JSONL: {LOG_PATH}")
            continue

        if cmd.strip() == ":servers":
            sids = list(mcp_mgr._sessions.keys())
            console.print(f"Servers: {', '.join(sids) if sids else '(ninguno)'}")
            continue

        if cmd.startswith(":tools"):
            parts = cmd.split()
            server = parts[1] if len(parts) > 1 else None
            tools = await mcp_mgr.list_tools(server)
            for sid, arr in tools.items():
                console.print(f"[bold]{sid}[/] — {len(arr)} tools")
                for t in arr:
                    console.print(f"  - {t.get('name')}: {t.get('description','')}")
            continue

        if cmd.startswith(":schema "):
            try:
                _, sid, tool = cmd.split(maxsplit=2)
            except ValueError:
                console.print("[red]Uso:[/] :schema <server> <tool>")
                continue
            try:
                info = await mcp_mgr.get_schema(sid, tool)
                console.print(f"[bold]{sid}:{tool}[/] — {info.get('description','')}")
                console.print_json(data=info.get("input_schema"))
            except Exception as e:
                console.print(f"[red]No se pudo obtener esquema:[/] {e}")
            continue

        if cmd.startswith(":call "):
            try:
                _, sid, tool, *rest = cmd.split(maxsplit=3)
            except ValueError:
                console.print("[red]Uso:[/] :call <server> <tool> <json-args>")
                continue
            args: Dict[str, Any] = {}
            if rest:
                try:
                    args = json.loads(rest[0])
                except json.JSONDecodeError as e:
                    console.print(f"[red]JSON inválido:[/] {e}")
                    continue
            try:
                res = await mcp_mgr.call_tool(sid, tool, args)
                console.print_json(data=res)
            except Exception as e:
                console.print(f"[red]Error en tools/call:[/] {e}")
            continue

        if cmd.strip() == ":scenario":
            steps = await mcp_mgr.run_inciso4_scenario()
            console.print("[bold green]Escenario inciso 4 completado (parcial si faltó Git). Pasos:[/]")
            for s in steps:
                console.print(f"  - {s}")
            continue

        if llm is None:
            console.print("[red]LLM no configurado; configura GOOGLE_API_KEY en .env[/]")
        else:
            out = await agent.run(cmd)
            console.print(f"[bold blue]Respuesta:[/] {out.get('final')}")
            if out.get("trace"):
                console.print("[dim]Herramientas utilizadas:[/]")
                for t in out["trace"]:
                    if t.get("type") == "call":
                        console.print(f"  - {t['server_id']}::{t['name']} → ok")
                    elif t.get("type") == "error":
                        console.print(f"  - {t['server_id']}::{t['name']} → ERROR: {t.get('error')}")
    await mcp_mgr.close()

def main():
    try:
        asyncio.run(run_cli())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
