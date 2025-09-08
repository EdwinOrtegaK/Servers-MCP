# server/main.py
from __future__ import annotations

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
import aiohttp
import os, random
from dotenv import load_dotenv
from typing import Literal
from .github_client import GitHubClient

load_dotenv()
app = FastAPI(title="MCP Remote VGC Demo")

PROTOCOL = "2025-06-18"
AUTH_TOKEN = os.getenv("AUTH_TOKEN")
SERVER_INFO = {"name": os.getenv("MCP_SERVER_NAME", "vgc-remote"),
               "version": os.getenv("MCP_SERVER_VERSION", "0.1.0")}

# Definición de herramientas
TOOLS = [
    {
        "name": "echo",
        "description": "Devuelve exactamente el texto enviado",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False
        },
    },
    {
        "name": "random_pokemon",
        "description": "Devuelve un Pokémon aleatorio (opcional: filtrar por tipo)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "type_filter": {"type": "string", "description": "Tipo a filtrar (e.g. 'water','fire')"}
            },
            "additionalProperties": False
        },
    },
    {
        "name": "github_repo_info",
        "description": "Metadatos clave de un repositorio (stars, forks, branch por defecto, etc.).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "owner": {"type": "string"},
                "repo": {"type": "string"}
            },
            "required": ["owner", "repo"],
            "additionalProperties": False
        }
    },
    {
        "name": "github_list_issues",
        "description": "Lista issues (no PRs) con filtros básicos.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "owner": {"type": "string"},
                "repo": {"type": "string"},
                "state": {"type": "string", "enum": ["open", "closed", "all"], "default": "open"},
                "labels": {"type": "array", "items": {"type": "string"}},
                "assignee": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}
            },
            "required": ["owner", "repo"],
            "additionalProperties": False
        }
    },
    {
        "name": "github_get_file",
        "description": "Lee un archivo de un repo y devuelve su contenido si es texto.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "owner": {"type": "string"},
                "repo": {"type": "string"},
                "path": {"type": "string"},
                "ref": {"type": "string", "default": "HEAD"}
            },
            "required": ["owner", "repo", "path"],
            "additionalProperties": False
        }
    },
    {
        "name": "github_search_issues",
        "description": "Busca issues y PRs usando la sintaxis de búsqueda de GitHub.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}
            },
            "required": ["query"],
            "additionalProperties": False
        }
    },
    {
        "name": "github_pr_status",
        "description": "Estado de un PR (mergeable, draft) y resumen de check-runs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "owner": {"type": "string"},
                "repo": {"type": "string"},
                "number": {"type": "integer"}
            },
            "required": ["owner", "repo", "number"],
            "additionalProperties": False
        }
    },
    {
        "name": "github_compare",
        "description": "Compara dos refs (base...head) y resume cambios.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "owner": {"type": "string"},
                "repo": {"type": "string"},
                "base": {"type": "string"},
                "head": {"type": "string"}
            },
            "required": ["owner", "repo", "base", "head"],
            "additionalProperties": False
        }
    },
]

POKEDEX = [
    {"name": "Pikachu", "types": ["electric"]},
    {"name": "Charizard", "types": ["fire", "flying"]},
    {"name": "Gyarados", "types": ["water", "flying"]},
    {"name": "Landorus-Therian", "types": ["ground", "flying"]},
    {"name": "Incineroar", "types": ["fire", "dark"]},
    {"name": "Amoonguss", "types": ["grass", "poison"]},
    {"name": "Iron Hands", "types": ["fighting", "electric"]},
]

class RepoInfoArgs(BaseModel):
    owner: str
    repo: str

class ListIssuesArgs(BaseModel):
    owner: str
    repo: str
    state: Literal["open", "closed", "all"] = "open"
    labels: list[str] | None = None
    assignee: str | None = None
    limit: int = Field(default=20, ge=1, le=100)

class GetFileArgs(BaseModel):
    owner: str
    repo: str
    path: str
    ref: str | None = "HEAD"

class SearchIssuesArgs(BaseModel):
    query: str
    limit: int = Field(default=20, ge=1, le=100)

class PRStatusArgs(BaseModel):
    owner: str
    repo: str
    number: int

class CompareArgs(BaseModel):
    owner: str
    repo: str
    base: str
    head: str

def handle_tool(name: str, args: dict):
    if name == "echo":
        text = args.get("text", "")
        return {"content": [{"type": "text", "text": text}]}

    if name == "random_pokemon":
        t = (args or {}).get("type_filter")
        pool = [p for p in POKEDEX if not t or t.lower() in p["types"]]
        if not pool:
            return {"content": [{"type": "text", "text": "Sin coincidencias para ese tipo."}]}
        pick = random.choice(pool)
        return {"content": [{"type": "text", "text": f"Sorteo: {pick['name']} ({'/'.join(pick['types'])})"}]}

    # herramienta desconocida
    return {"content": [{"type": "text", "text": f"Herramienta desconocida: {name}"}]}

# Utilidades JSON-RPC
def jsonrpc_result(id_, result):
    return {"jsonrpc": "2.0", "id": id_, "result": result}

def jsonrpc_error(id_, code=-32600, message="Invalid Request"):
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}

def check_auth(req: Request):
    if not AUTH_TOKEN:
        return True
    auth = req.headers.get("authorization", "")
    if auth.startswith("Bearer ") and auth.split(" ", 1)[1] == AUTH_TOKEN:
        return True
    raise HTTPException(status_code=401, detail="Unauthorized")

def mcp_text_result(text: str, data=None) -> dict:
    res = {"content": [{"type": "text", "text": text}]}
    if data is not None:
        res["data"] = data
    return res

# Endpoints
@app.get("/healthz")
def health():
    return {"ok": True, "server": SERVER_INFO}

@app.post("/")
async def rpc(req: Request):
    check_auth(req)
    try:
        body = await req.json()
    except Exception:
        return JSONResponse(jsonrpc_error(None, message="Invalid JSON"), status_code=400)

    # Soporta un solo objeto JSON-RPC por request
    method = body.get("method")
    id_ = body.get("id")
    params = body.get("params") or {}
    is_notification = "id" not in body

    if method == "initialize":
        result = {
            "protocolVersion": PROTOCOL,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        }
        return JSONResponse(jsonrpc_result(id_, result))

    if method == "initialized":
        # Notificación sin respuesta (pero HTTP necesita 204/200 vacío)
        return Response(status_code=204)

    if method == "tools/list":
        return JSONResponse(jsonrpc_result(id_, {"tools": TOOLS}))

    if method == "tools/call":
        params = body.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        
        # Triviales (sync)
        if name in ("echo", "random_pokemon"):
            tool_result = handle_tool(name, arguments)
            return JSONResponse(jsonrpc_result(id_, tool_result))

        # GitHub (async con aiohttp + GitHubClient)
        gh = GitHubClient()
        timeout = aiohttp.ClientTimeout(total=25, connect=5)

        try:
            if name == "github_repo_info":
                a = RepoInfoArgs(**arguments)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    data = await gh.repo_summary(session, a.owner, a.repo)
                text = (f"{data['full_name']} — ⭐ {data['stars']} | 🍴 {data['forks']} | "
                        f"issues {data['open_issues']} | default: {data['default_branch']}")
                return JSONResponse(jsonrpc_result(id_, mcp_text_result(text, data)))

            elif name == "github_list_issues":
                a = ListIssuesArgs(**arguments)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    items = await gh.list_issues(session, a.owner, a.repo, a.state, a.labels, a.assignee, a.limit)
                if not items:
                    text = f"Sin issues para {a.owner}/{a.repo} con esos filtros."
                else:
                    lines = []
                    for it in items[:10]:
                        lbls = ",".join(it.get("labels") or []) or "-"
                        lines.append(f"#{it['number']} {it['title']} [{it['state']}] @{it.get('author','?')} ({lbls})")
                    more = "" if len(items) <= 10 else f"\n… y {len(items)-10} más"
                    text = f"Issues en {a.owner}/{a.repo} (state={a.state}):\n" + "\n".join(lines) + more
                return JSONResponse(jsonrpc_result(id_, mcp_text_result(text, items)))

            elif name == "github_get_file":
                a = GetFileArgs(**arguments)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    data = await gh.get_file(session, a.owner, a.repo, a.path, a.ref)
                preview = (data.get("content") or "")[:500]
                tail = "" if not data.get("content") or len(data["content"]) <= 500 else "\n…(truncado)"
                text = f"{a.owner}/{a.repo}@{a.ref or 'HEAD'} — {a.path} (size={data.get('size')}):\n{preview}{tail}"
                return JSONResponse(jsonrpc_result(id_, mcp_text_result(text, data)))

            elif name == "github_search_issues":
                a = SearchIssuesArgs(**arguments)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    items = await gh.search_issues(session, a.query, a.limit)
                lines = [f"{it['repo']} #{it.get('number','?')}: {it['title']}" for it in items[:10]]
                more = "" if len(items) <= 10 else f"\n… y {len(items)-10} más"
                text = "Resultados de búsqueda:\n" + ("\n".join(lines) if lines else "— vacío —") + more
                return JSONResponse(jsonrpc_result(id_, mcp_text_result(text, items)))

            elif name == "github_pr_status":
                a = PRStatusArgs(**arguments)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    info = await gh.pr_status(session, a.owner, a.repo, a.number)
                checks = info.get("checks_summary", {})
                text = (f"PR #{info['number']} {info['title']} — state={info['state']}, "
                        f"mergeable={info['mergeable']}, draft={info['draft']}, "
                        f"checks={checks.get('total',0)} ({','.join(checks.get('statuses',[])) or '-'})")
                return JSONResponse(jsonrpc_result(id_, mcp_text_result(text, info)))

            elif name == "github_compare":
                a = CompareArgs(**arguments)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    comp = await gh.compare(session, a.owner, a.repo, a.base, a.head)
                files = comp.get("files", [])
                first = "\n".join([f"{f['status']:>9}  +{f['additions']}/-{f['deletions']}  {f['filename']}"
                                   for f in files[:10]])
                more = "" if len(files) <= 10 else f"\n… y {len(files)-10} más"
                text = (f"Diff {a.base}...{a.head} — ahead {comp['ahead_by']}, behind {comp['behind_by']}, "
                        f"commits {comp['total_commits']}\n{first}{more}")
                return JSONResponse(jsonrpc_result(id_, mcp_text_result(text, comp)))

            else:
                return JSONResponse(jsonrpc_error(id_, code=-32601, message=f"Tool not found: {name}"), status_code=400)

        except ValidationError as ve:
            return JSONResponse(jsonrpc_error(id_, code=-32602, message=f"Invalid params: {ve}"), status_code=400)
        except aiohttp.ClientResponseError as ce:
            return JSONResponse(jsonrpc_error(id_, code=-32000, message=f"GitHub HTTP {ce.status}: {ce.message}"), status_code=502)
        except Exception as e:
            return JSONResponse(jsonrpc_error(id_, code=-32001, message=f"Unhandled error: {e}"), status_code=500)

    # Método desconocido
    if is_notification:
        return Response(status_code=204)
    return JSONResponse(jsonrpc_error(id_, code=-32601, message="Method not found"), status_code=400)
