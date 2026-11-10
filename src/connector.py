import importlib
from abc import ABC, abstractmethod
from typing import List

from src.models import MoverChange, UserProfile


class BaseConnector(ABC):
    """Protocolo base que todo conector SCIM debe implementar.

    Un conector traduce los perfiles de usuario y los cambios del ciclo
    Joiner-Mover-Leaver a payloads SCIM 2.0 concretos. La implementación
    incluida en connectors/example.py sirve como referencia.
    """

    @abstractmethod
    def build_create_payload(self, user: UserProfile) -> dict:
        """Construye el payload SCIM para crear un usuario (Joiner).

        Debe incluir el schema de User y mapear los atributos del perfil
        a atributos SCIM estándar: userName, name.givenName,
        name.familyName, emails, title y department (vía extensión
        enterprise urn:ietf:params:scim:schemas:extension:enterprise:2.0:User).
        """
        raise NotImplementedError

    @abstractmethod
    def build_patch_payload(
        self, user: UserProfile, changes: List[MoverChange]
    ) -> List[dict]:
        """Construye la lista de operaciones SCIM PatchOp para un Mover.

        Cada operación tiene la forma:
        {"op": "Replace", "path": "<atributo>", "value": <nuevo_valor>}
        """
        raise NotImplementedError

    @abstractmethod
    def build_delete_payload(self, user: UserProfile) -> dict:
        """Construye el payload para eliminar un usuario (Leaver).

        La identidad del usuario viaja en la URL (user_id), por lo que
        el payload retornado es un diccionario vacío.
        """
        raise NotImplementedError

    @abstractmethod
    def get_name(self) -> str:
        """Retorna el nombre identificativo del conector."""
        raise NotImplementedError

    @abstractmethod
    def get_version(self) -> str:
        """Retorna la versión del conector."""
        raise NotImplementedError


def load_connector(name: str) -> BaseConnector:
    """Carga dinámicamente un conector desde connectors/{name}.py.

    Importa el módulo, localiza la clase que hereda de BaseConnector y
    retorna una instancia. Lanza ImportError si el módulo no existe y
    ValueError si no contiene una implementación válida.
    """
    module_path = f"src.connectors.{name}"
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise ImportError(
            f"No se pudo importar el conector '{name}' desde {module_path}"
        ) from exc

    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if (
            isinstance(attr, type)
            and issubclass(attr, BaseConnector)
            and attr is not BaseConnector
        ):
            return attr()

    raise ValueError(
        f"El módulo {module_path} no define ninguna subclase de BaseConnector"
    )
