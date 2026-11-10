from __future__ import annotations

from typing import Any, Dict, List

from ..connector import BaseConnector
from ..models import MoverChange, UserProfile


# URNs de los esquemas SCIM 2.0 utilizados por el conector
SCHEMA_USER = "urn:ietf:params:scim:schemas:core:2.0:User"
SCHEMA_ENTERPRISE = "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"


# Mapeo de atributos lógicos del ciclo de vida a rutas SCIM 2.0.
# Las claves son los nombres usados en los escenarios YAML; los valores
# son las rutas de atributo que entiende el servidor SCIM.
FIELD_MAPPING: Dict[str, str] = {
    "department": f"{SCHEMA_ENTERPRISE}:department",
    "title": "title",
    "manager": f"{SCHEMA_ENTERPRISE}:manager.value",
    "email": "userName",
    "given_name": "name.givenName",
    "family_name": "name.familyName",
    "active": "active",
}


class ExampleConnector(BaseConnector):
    """Conector de referencia que traduce eventos JML a payloads SCIM 2.0.

    Sirve como plantilla para implementar conectores contra proveedores
    reales (IdentityNow, Azure AD, etc.): basta con respetar el protocolo
    definido en ``BaseConnector`` y ajustar el mapeo de campos.
    """

    def get_name(self) -> str:
        return "ExampleConnector"

    def get_version(self) -> str:
        return "1.0"

    def build_create_payload(self, profile: UserProfile) -> Dict[str, Any]:
        """Construye el cuerpo de un POST /Users con el perfil completo."""
        payload: Dict[str, Any] = {
            "schemas": [SCHEMA_USER, SCHEMA_ENTERPRISE],
            "userName": profile.email,
            "name": {
                "givenName": profile.given_name,
                "familyName": profile.family_name,
            },
            "emails": [
                {
                    "value": profile.email,
                    "type": "work",
                    "primary": True,
                }
            ],
            "title": profile.title,
            "active": profile.active,
            SCHEMA_ENTERPRISE: {
                "department": profile.department,
                "manager": (
                    {"value": profile.manager} if profile.manager else None
                ),
            },
        }
        return payload

    def build_patch_payload(self, changes: List[MoverChange]) -> Dict[str, Any]:
        """Convierte cada cambio de un Mover en una operación Replace SCIM."""
        operations: List[Dict[str, Any]] = []
        for change in changes:
            path = FIELD_MAPPING.get(change.field, change.field)
            operations.append(
                {
                    "op": "replace",
                    "path": path,
                    "value": change.new_value,
                }
            )
        return {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": operations,
        }

    def build_delete_payload(self) -> Dict[str, Any]:
        """El borrado SCIM no requiere cuerpo; se devuelve un dict vacío."""
        return {}
