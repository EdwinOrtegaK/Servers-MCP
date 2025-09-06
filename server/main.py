# server/main.py
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
import os, random
import aiohttp

app = FastAPI(title="MCP Remote VGC Demo")
SERVER_INFO = {"name": "vgc-remote", "version": "0.1.0"}
PROTOCOL = "2025-06-18"
AUTH_TOKEN = os.getenv("AUTH_TOKEN")  # opcional

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
        tool_result = handle_tool(name, arguments)
        # Formato típico de MCP
        return JSONResponse(jsonrpc_result(id_, tool_result))

    # Método desconocido
    if is_notification:
        return Response(status_code=204)
    return JSONResponse(jsonrpc_error(id_, code=-32601, message="Method not found"), status_code=400)

# Entrada con Uvicorn en Cloud Run/Local
# uvicorn server.main:app --host 0.0.0.0 --port 8080
