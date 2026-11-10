import os
import json
from datetime import datetime
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .audit import AuditLogger


TOOL_NAME = "LifecycleTracer"
TOOL_VERSION = "1.0.0"


class ReportRenderer:
    """Genera un informe HTML a partir de los eventos registrados en la auditoría."""

    def __init__(self, audit_logger: AuditLogger, template_dir: str = "src/templates") -> None:
        self.audit_logger = audit_logger
        self.template_dir = template_dir
        # Configuramos Jinja2 con autoescape para evitar inyección de HTML en los campos
        self.env = Environment(
            loader=FileSystemLoader(self.template_dir),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def _serialize_event(self, event: Any) -> dict:
        """Convierte un AuditEvent en un dict con payloads y deltas ya parseados."""
        data = event.model_dump() if hasattr(event, "model_dump") else dict(event)
        for campo in ("payload", "response", "delta"):
            valor = data.get(campo)
            if isinstance(valor, str) and valor:
                try:
                    data[campo] = json.loads(valor)
                except (json.JSONDecodeError, TypeError):
                    # Si no es JSON válido dejamos el valor original
                    data[campo] = valor
        return data

    def generate(self, output_path: str) -> str:
        """Renderiza la plantilla y escribe el HTML resultante. Devuelve la ruta."""
        template = self.env.get_template("report.html")

        events = [self._serialize_event(e) for e in self.audit_logger.get_events()]
        summary = self.audit_logger.get_summary()

        html = template.render(
            events=events,
            summary=summary,
            generated_at=datetime.now().isoformat(),
            tool_name=TOOL_NAME,
            tool_version=TOOL_VERSION,
        )

        directorio = os.path.dirname(os.path.abspath(output_path))
        if directorio:
            os.makedirs(directorio, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

        return output_path
