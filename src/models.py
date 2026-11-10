from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserProfile(BaseModel):
    """Perfil de identidad que viaja por el ciclo Joiner-Mover-Leaver."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    username: str
    email: EmailStr
    first_name: str
    last_name: str
    department: str
    title: str
    manager: str | None = None
    active: bool = True
    extra: dict[str, Any] = Field(default_factory=dict)


class MoverChange(BaseModel):
    """Cambio concreto aplicado sobre un atributo del usuario en fase Mover."""

    model_config = ConfigDict(from_attributes=True)

    field: str
    old_value: str
    new_value: str


class JoinerEvent(BaseModel):
    """Alta de un nuevo usuario en el directorio."""

    model_config = ConfigDict(from_attributes=True)

    user: UserProfile


class MoverEvent(BaseModel):
    """Modificación de atributos de un usuario existente."""

    model_config = ConfigDict(from_attributes=True)

    user: UserProfile
    changes: list[MoverChange] = Field(default_factory=list)


class LeaverEvent(BaseModel):
    """Baja de un usuario, ya sea por desactivación o borrado definitivo."""

    model_config = ConfigDict(from_attributes=True)

    user: UserProfile
    leaver_action: Literal["deactivate", "delete"] = "deactivate"


class Scenario(BaseModel):
    """Escenario completo de simulación cargado desde YAML."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    description: str
    users: list[UserProfile] = Field(default_factory=list)
    joiner_events: list[JoinerEvent] = Field(default_factory=list)
    mover_events: list[MoverEvent] = Field(default_factory=list)
    leaver_events: list[LeaverEvent] = Field(default_factory=list)


class AuditEvent(BaseModel):
    """Registro inmutable de una interacción SCIM con su delta asociado."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    phase: str
    username: str
    http_method: str
    endpoint: str
    status_code: int
    payload: dict[str, Any] = Field(default_factory=dict)
    response: dict[str, Any] = Field(default_factory=dict)
    delta: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
