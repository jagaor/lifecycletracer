import threading
import uuid
import re
from datetime import datetime, timezone
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

# Prefijo base para todos los endpoints SCIM 2.0
SCIM_PREFIX = "/scim/v2"

# Almacén de usuarios en memoria: id -> dict con el recurso SCIM
users: dict[str, dict] = {}

# Servidor uvicorn y hilo de fondo para poder arrancarlo y pararlo desde el CLI
_server: uvicorn.Server | None = None
_server_thread: threading.Thread | None = None

app = FastAPI(title="LifecycleTracer Mock SCIM Server")


def _now_iso() -> str:
    """Devuelve la fecha actual en formato ISO 8601 UTC (SCIM usa este formato)."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _build_user_resource(user_id: str, payload: dict) -> dict:
    """Construye un recurso User SCIM 2.0 completo a partir del payload de entrada."""
    now = _now_iso()
    resource = {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
        "id": user_id,
        "userName": payload.get("userName", ""),
        "name": payload.get("name", {}),
        "emails": payload.get("emails", []),
        "active": payload.get("active", True),
        "meta": {
            "resourceType": "User",
            "created": now,
            "lastModified": now,
            "location": f"{SCIM_PREFIX}/Users/{user_id}",
        },
    }
    # Copiar atributos extra que no sean de metadatos
    for key, value in payload.items():
        if key not in resource and key != "meta":
            resource[key] = value
    return resource


def _apply_patch_operations(user: dict, operations: list[dict]) -> dict:
    """Aplica operaciones PatchOp (RFC 7644) sobre un recurso User."""
    for op in operations:
        op_type = op.get("op", "").lower()
        path = op.get("path", "")
        value = op.get("value")
        # Normalizar el path: eliminar prefijo de esquema si existe
        if isinstance(path, str) and path.startswith("urn:ietf:params:scim:schemas:core:2.0:User:"):
            path = path.split(":")[-1]
        if op_type == "add" or op_type == "replace":
            if path:
                # Asignación directa de atributo simple
                user[path] = value
            elif isinstance(value, dict):
                # Sin path: el value es un objeto con atributos a fusionar
                user.update(value)
        elif op_type == "remove":
            if path and path in user:
                del user[path]
    user["meta"]["lastModified"] = _now_iso()
    return user


@app.post(f"{SCIM_PREFIX}/Users", status_code=status.HTTP_201_CREATED)
async def create_user(request: Request) -> JSONResponse:
    """Crea un nuevo usuario SCIM y devuelve 201 con cabecera Location."""
    payload = await request.json()
    user_id = str(uuid.uuid4())
    resource = _build_user_resource(user_id, payload)
    users[user_id] = resource
    location = resource["meta"]["location"]
    return JSONResponse(
        content=resource,
        status_code=status.HTTP_201_CREATED,
        headers={"Location": location},
    )


@app.get(f"{SCIM_PREFIX}/Users")
async def list_users(filter: str | None = None) -> JSONResponse:
    """Lista usuarios SCIM. Soporta filtro simple sobre userName (eq)."""
    result = list(users.values())
    if filter:
        # Parseo muy básico: userName eq "valor"
        match = re.match(r'userName\s+eq\s+"([^"]+)"', filter.strip())
        if match:
            target = match.group(1)
            result = [u for u in result if u.get("userName") == target]
    return JSONResponse(
        content={
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
            "totalResults": len(result),
            "Resources": result,
            "startIndex": 1,
            "itemsPerPage": len(result),
        }
    )


@app.get(f"{SCIM_PREFIX}/Users/{{user_id}}")
async def get_user(user_id: str) -> JSONResponse:
    """Obtiene un usuario por id. Devuelve 404 si no existe."""
    user = users.get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return JSONResponse(content=user)


@app.patch(f"{SCIM_PREFIX}/Users/{{user_id}}")
async def patch_user(user_id: str, request: Request) -> JSONResponse:
    """Aplica operaciones PatchOp (Add, Replace, Remove) sobre un usuario."""
    user = users.get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    payload = await request.json()
    operations = payload.get("Operations", [])
    updated = _apply_patch_operations(user, operations)
    users[user_id] = updated
    return JSONResponse(content=updated)


@app.delete(f"{SCIM_PREFIX}/Users/{{user_id}}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: str) -> Response:
    """Elimina un usuario por id. Devuelve 204 sin cuerpo."""
    if user_id not in users:
        raise HTTPException(status_code=404, detail="User not found")
    del users[user_id]
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def start_mock_server(host: str = "127.0.0.1", port: int = 8765) -> threading.Thread:
    """Arranca el servidor mock en un hilo daemon y devuelve el hilo."""
    global _server, _server_thread
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    _server = uvicorn.Server(config)
    _server_thread = threading.Thread(target=_server.run, daemon=True)
    _server_thread.start()
    return _server_thread


def stop_mock_server() -> None:
    """Señaliza al servidor uvicorn que se detenga y espera al hilo."""
    global _server, _server_thread
    if _server is not None:
        _server.should_exit = True
    if _server_thread is not None:
        _server_thread.join(timeout=5)
    _server = None
    _server_thread = None
