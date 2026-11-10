import httpx
from typing import Any


class SCIMClient:
    """Cliente HTTP mínimo para interactuar con un endpoint SCIM 2.0.

    Encapsula las operaciones habituales sobre el recurso /Users y devuelve
    siempre una tupla (status_code, body) para que el llamador pueda auditar
    tanto éxitos como errores. Los errores HTTP (>=400) se propagan como
    httpx.HTTPStatusError tras invocar raise_for_status().
    """

    # Cabeceras por defecto exigidas por SCIM 2.0 (RFC 7644)
    SCIM_CONTENT_TYPE = "application/scim+json"
    PATCH_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:PatchOp"

    def __init__(self, base_url: str, token: str = "mock-token", timeout: float = 10.0) -> None:
        # Normalizamos la URL base eliminando la barra final para evitar dobles slashes
        self.base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": self.SCIM_CONTENT_TYPE,
            "Accept": self.SCIM_CONTENT_TYPE,
        }
        self._client = httpx.Client(
            base_url=self.base_url,
            headers=self._headers,
            timeout=timeout,
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> tuple[int, dict]:
        """Ejecuta la petición y normaliza la respuesta a (status, body)."""
        response = self._client.request(method, path, **kwargs)
        # Lanzamos excepción si el servidor responde con error
        response.raise_for_status()
        # Algunos endpoints (DELETE) pueden devolver cuerpo vacío
        try:
            body = response.json() if response.content else {}
        except ValueError:
            body = {"raw": response.text}
        return response.status_code, body

    def create_user(self, payload: dict) -> tuple[int, dict]:
        """Crea un usuario nuevo mediante POST /Users."""
        return self._request("POST", "/Users", json=payload)

    def get_user(self, user_id: str) -> tuple[int, dict]:
        """Recupera un usuario por su identificador."""
        return self._request("GET", f"/Users/{user_id}")

    def patch_user(self, user_id: str, operations: list[dict]) -> tuple[int, dict]:
        """Aplica operaciones PatchOp sobre un usuario existente."""
        body = {
            "schemas": [self.PATCH_SCHEMA],
            "Operations": operations,
        }
        return self._request("PATCH", f"/Users/{user_id}", json=body)

    def delete_user(self, user_id: str) -> tuple[int, dict]:
        """Elimina definitivamente un usuario (operación Leaver)."""
        return self._request("DELETE", f"/Users/{user_id}")

    def deactivate_user(self, user_id: str) -> tuple[int, dict]:
        """Desactiva un usuario sin borrarlo (operación Mover/Leaver lógica)."""
        operations = [
            {
                "op": "replace",
                "path": "active",
                "value": False,
            }
        ]
        return self.patch_user(user_id, operations)

    def list_users(self, filter_str: str = "") -> tuple[int, dict]:
        """Lista usuarios, opcionalmente aplicando un filtro SCIM."""
        params = {}
        if filter_str:
            params["filter"] = filter_str
        return self._request("GET", "/Users", params=params or None)

    def close(self) -> None:
        """Cierra el cliente subyacente y libera conexiones."""
        self._client.close()

    def __enter__(self) -> "SCIMClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
