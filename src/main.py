"""CLI principal de LifecycleTracer usando Typer.

Expone los comandos simulate, report y validate. Toda la salida se
formatea con Rich. El mock SCIM se arranca en un hilo de fondo para
que el CLI y el servidor convivan en el mismo proceso.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
import yaml
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from .engine import EventEngine
from .mock_server import start_mock_server
from .models import Scenario
from .report import ReportRenderer

app = typer.Typer(help="LifecycleTracer: simula y audita el ciclo Joiner-Mover-Leaver sobre SCIM 2.0")
console = Console()


def _resolve_scenario(scenario: str) -> Path:
    """Resuelve una ruta o un nombre predefinido dentro de scenarios/."""
    path = Path(scenario)
    if path.exists():
        return path
    candidate = Path("scenarios") / f"{scenario}.yaml"
    if candidate.exists():
        return candidate
    raise typer.BadParameter(f"Escenario no encontrado: {scenario}")


@app.command()
def simulate(
    scenario: str = typer.Option("full-lifecycle", "--scenario", "-s", help="Ruta YAML o nombre predefinido en scenarios/"),
    user_count: int = typer.Option(3, "--user-count", "-n", help="Número de usuarios a simular"),
    scim_url: str = typer.Option("http://127.0.0.1:8765/scim/v2", "--scim-url", help="URL base del endpoint SCIM 2.0"),
    connector: str = typer.Option("example", "--connector", "-c", help="Conector a usar para transformar eventos"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Muestra detalles adicionales por evento"),
) -> None:
    """Ejecuta una simulación JML completa contra el mock SCIM."""
    scenario_path = _resolve_scenario(scenario)
    console.rule(f"[bold]Simulación: {scenario_path.name}[/]")

    # Arranca el mock SCIM en un hilo de fondo (idempotente si ya está activo).
    start_mock_server(host="127.0.0.1", port=8765)
    console.print(f"[green]Mock SCIM escuchando en[/] {scim_url}")

    engine = EventEngine(scim_url=scim_url, connector_name=connector)
    results = engine.run_scenario(scenario_path, user_count=user_count)

    # Tabla resumen con los eventos registrados durante la simulación.
    table = Table(title="Eventos JML registrados", show_lines=False)
    table.add_column("Timestamp", style="dim")
    table.add_column("Fase", style="cyan")
    table.add_column("Usuario")
    table.add_column("Operación HTTP", style="magenta")
    table.add_column("Status", justify="right")
    table.add_column("Delta", style="green")

    for ev in results:
        delta = json.dumps(ev.delta, ensure_ascii=False) if ev.delta else "-"
        table.add_row(
            ev.timestamp.isoformat(timespec="seconds"),
            ev.phase,
            ev.user_name,
            ev.http_method or "-",
            str(ev.status_code or "-"),
            delta,
        )
    console.print(table)

    if verbose:
        for ev in results:
            console.print(f"[dim]{ev.timestamp.isoformat()}[/] {ev.phase} -> {ev.detail}")

    # Genera el informe HTML al finalizar la simulación.
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = Path("reports") / f"lifecycle_{timestamp}.html"
    ReportRenderer(db_path=engine.audit.db_path).generate(output)
    console.print(f"[bold green]Informe generado:[/] {output}")


@app.command()
def report(
    db: str = typer.Option("audit.db", "--db", help="Ruta a la base de datos de auditoría SQLite"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Ruta del HTML de salida"),
) -> None:
    """Genera un informe HTML a partir de una base de auditoría existente."""
    db_path = Path(db)
    if not db_path.exists():
        console.print(f"[red]No existe la base de auditoría:[/] {db_path}")
        raise typer.Exit(code=1)

    if output is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path("reports") / f"lifecycle_{timestamp}.html"
    else:
        output_path = Path(output)

    ReportRenderer(db_path=db_path).generate(output_path)
    console.print(f"[bold green]Informe generado:[/] {output_path}")


@app.command()
def validate(
    scenario: str = typer.Option(..., "--scenario", "-s", help="Ruta YAML o nombre predefinido en scenarios/"),
) -> None:
    """Valida un escenario YAML contra el modelo Pydantic."""
    scenario_path = _resolve_scenario(scenario)
    try:
        raw = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
        Scenario.model_validate(raw)
    except ValidationError as exc:
        console.print(f"[red]Escenario inválido:[/] {scenario_path}")
        for err in exc.errors():
            console.print(f"  - {err['loc']}: {err['msg']}")
        raise typer.Exit(code=1)
    except Exception as exc:  # YAML malformado u otro error de lectura
        console.print(f"[red]Error al leer el escenario:[/] {exc}")
        raise typer.Exit(code=1)

    console.print(f"[bold green]OK[/] Escenario válido: {scenario_path}")


if __name__ == "__main__":
    app()
