"""Módulo de auditoría persistente sobre SQLite.

Registra cada evento del ciclo Joiner-Mover-Leaver con su petición SCIM,
respuesta, delta de atributos y posible error, permitiendo reconstruir
la traza completa de una simulación.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any, Optional

from .models import AuditEvent


class AuditLogger:
    """Persistencia de eventos de auditoría en una base SQLite."""

    def __init__(self, db_path: str = "audit.db") -> None:
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self) -> None:
        """Crea la tabla audit_events si no existe."""
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                phase TEXT NOT NULL,
                username TEXT NOT NULL,
                http_method TEXT,
                endpoint TEXT,
                status_code INTEGER,
                payload TEXT,
                response TEXT,
                delta TEXT,
                error TEXT
            )
            """
        )
        self._conn.commit()

    @staticmethod
    def _serialize(value: Optional[Any]) -> Optional[str]:
        """Serializa a JSON cualquier estructura; None se mantiene como None."""
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False, default=str)

    def log(self, event: AuditEvent) -> None:
        """Inserta un evento de auditoría en la base de datos."""
        self._conn.execute(
            """
            INSERT OR REPLACE INTO audit_events
                (id, timestamp, phase, username, http_method, endpoint,
                 status_code, payload, response, delta, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.id,
                event.timestamp.isoformat()
                if isinstance(event.timestamp, datetime)
                else str(event.timestamp),
                event.phase,
                event.username,
                event.http_method,
                event.endpoint,
                event.status_code,
                self._serialize(event.payload),
                self._serialize(event.response),
                self._serialize(event.delta),
                event.error,
            ),
        )
        self._conn.commit()

    def get_all_events(self) -> list[AuditEvent]:
        """Devuelve todos los eventos ordenados por timestamp ascendente."""
        cursor = self._conn.execute(
            "SELECT * FROM audit_events ORDER BY timestamp ASC"
        )
        eventos: list[AuditEvent] = []
        for row in cursor.fetchall():
            eventos.append(self._row_to_event(row))
        return eventos

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> AuditEvent:
        """Reconstruye un AuditEvent desde una fila SQLite."""

        def _load(value: Optional[str]) -> Optional[Any]:
            if value is None:
                return None
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value

        return AuditEvent(
            id=row["id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            phase=row["phase"],
            username=row["username"],
            http_method=row["http_method"],
            endpoint=row["endpoint"],
            status_code=row["status_code"],
            payload=_load(row["payload"]),
            response=_load(row["response"]),
            delta=_load(row["delta"]),
            error=row["error"],
        )

    def get_summary(self) -> dict:
        """Calcula métricas agregadas de la traza de auditoría."""
        events = self.get_all_events()
        total = len(events)
        successful = sum(
            1 for e in events if e.status_code is not None and e.status_code < 400
        )
        failed = total - successful

        by_phase: dict[str, int] = {}
        for e in events:
            by_phase[e.phase] = by_phase.get(e.phase, 0) + 1

        duration = 0.0
        if len(events) >= 2:
            first = events[0].timestamp
            last = events[-1].timestamp
            if isinstance(first, datetime) and isinstance(last, datetime):
                duration = (last - first).total_seconds()

        return {
            "total_events": total,
            "successful": successful,
            "failed": failed,
            "by_phase": by_phase,
            "duration_seconds": duration,
        }

    def close(self) -> None:
        """Cierra la conexión con la base de datos."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None  # type: ignore[assignment]

    def __enter__(self) -> "AuditLogger":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
