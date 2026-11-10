"""Módulo EventEngine: orquesta la simulación del ciclo Joiner-Mover-Leaver.

Recorre los usuarios y fases definidos en un escenario, invoca al conector
para construir los payloads SCIM y ejecuta las llamadas HTTP contra el
servidor SCIM a través de SCIMClient. Cada operación se audita mediante
AuditLogger, incluyendo errores HTTP sin detener la simulación.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from audit import AuditLogger
from connector import BaseConnector
from models import Scenario, User, UserChanges
from scim_client import SCIMClient


@dataclass
class AuditEvent:
    """Evento de auditoría generado por cada operación SCIM."""

    id: str
    timestamp: datetime
    phase: str
    username: str
    http_method: str
    endpoint: str
    status_code: int
    payload: dict[str, Any] = field(default_factory=dict)
    response: dict[str, Any] = field(default_factory=dict)
    delta: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class EventEngine:
    """Motor de simulación JML que ejecuta escenarios contra un endpoint SCIM."""

    def __init__(
        self,
        scim_url: str,
        connector: BaseConnector,
        audit_logger: AuditLogger,
    ) -> None:
        self.scim_client = SCIMClient(base_url=scim_url)
        self.connector = connector
        self.audit_logger = audit_logger

    def run_scenario(self, scenario: Scenario) -> list[AuditEvent]:
        """Ejecuta todas las fases del escenario y devuelve los eventos auditados."""
        events: list[AuditEvent] = []

        for user in scenario.users:
            for phase in scenario.phases:
                if phase == "joiner":
                    events.append(self._run_joiner(user))
                elif phase == "mover":
                    events.extend(self._run_mover(user, scenario.changes.get(user.username, {})))
                elif phase == "leaver":
                    events.append(self._run_leaver(user, scenario.leaver_action))

        return events

    def _run_joiner(self, user: User) -> AuditEvent:
        """Crea el usuario en el sistema destino mediante POST SCIM."""
        payload = self.connector.build_create_payload(user)
        return self._execute(
            phase="joiner",
            username=user.username,
            method="POST",
            endpoint="/scim/v2/Users",
            payload=payload,
            call=lambda: self.scim_client.create_user(payload),
        )

    def _run_mover(self, user: User, changes: dict[str, Any]) -> list[AuditEvent]:
        """Aplica cambios al usuario mediante PATCH SCIM, un evento por cambio."""
        events: list[AuditEvent] = []
        user_changes = UserChanges(username=user.username, attributes=changes)
        payload = self.connector.build_patch_payload(user, user_changes)
        events.append(
            self._execute(
                phase="mover",
                username=user.username,
                method="PATCH",
                endpoint=f"/scim/v2/Users/{user.external_id}",
                payload=payload,
                call=lambda: self.scim_client.patch_user(user.external_id, payload),
                delta=changes,
            )
        )
        return events

    def _run_leaver(self, user: User, leaver_action: str) -> AuditEvent:
        """Da de baja al usuario: desactiva o elimina según la acción configurada."""
        payload = self.connector.build_delete_payload(user)
        if leaver_action == "deactivate":
            return self._execute(
                phase="leaver",
                username=user.username,
                method="PATCH",
                endpoint=f"/scim/v2/Users/{user.external_id}",
                payload=payload,
                call=lambda: self.scim_client.deactivate_user(user.external_id),
            )
        return self._execute(
            phase="leaver",
            username=user.username,
            method="DELETE",
            endpoint=f"/scim/v2/Users/{user.external_id}",
            payload=payload,
            call=lambda: self.scim_client.delete_user(user.external_id),
        )

    def _execute(
        self,
        phase: str,
        username: str,
        method: str,
        endpoint: str,
        payload: dict[str, Any],
        call: Any,
        delta: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Ejecuta una llamada SCIM, captura errores y registra el evento de auditoría."""
        status_code = 0
        response_data: dict[str, Any] = {}
        error: str | None = None

        try:
            result = call()
            status_code = result.status_code
            response_data = result.json() if result.content else {}
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            error = f"HTTP {status_code}: {exc.response.text}"
        except httpx.HTTPError as exc:
            error = f"Error de red: {exc}"

        event = AuditEvent(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            phase=phase,
            username=username,
            http_method=method,
            endpoint=endpoint,
            status_code=status_code,
            payload=payload,
            response=response_data,
            delta=delta or {},
            error=error,
        )
        self.audit_logger.log(event)
        return event
