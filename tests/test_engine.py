import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from src.mock_server import app
from src.audit import AuditLogger
from src.connectors.example import ExampleConnector
from src.engine import EventEngine
from src.models import Scenario, User, AuditEvent
from src.scim_client import SCIMClient


@pytest.fixture
def mock_scim_server():
    """Arranca la app FastAPI con TestClient y la expone para el engine."""
    client = TestClient(app)
    yield client


@pytest.fixture
def mock_audit_logger():
    """AuditLogger con base de datos en memoria."""
    return AuditLogger(db_path=":memory:")


@pytest.fixture
def example_connector():
    """Instancia del conector de ejemplo."""
    return ExampleConnector()


@pytest.fixture
def simple_scenario():
    """Escenario simple con un usuario y fases joiner, mover, leaver."""
    return Scenario(
        name="simple-test",
        users=[
            User(
                id="u1",
                userName="test.user",
                givenName="Test",
                familyName="User",
                email="test.user@example.com",
                department="Engineering",
                active=True,
            )
        ],
        phases=["JOINER", "MOVER", "LEAVER"],
    )


@pytest.fixture
def engine(mock_scim_server, mock_audit_logger, example_connector):
    """EventEngine configurado con el mock server, audit logger y conector."""
    scim_client = SCIMClient(base_url="http://testserver/scim/v2", client=mock_scim_server)
    return EventEngine(scim_client=scim_client, audit_logger=mock_audit_logger, connector=example_connector)


def test_joiner_creates_user(engine, simple_scenario, mock_audit_logger):
    """El joiner debe crear un usuario y registrar un evento con phase='JOINER' y status 201."""
    engine.run_scenario(simple_scenario)
    events = mock_audit_logger.get_events()
    joiner_events = [e for e in events if e.phase == "JOINER"]
    assert len(joiner_events) == 1
    assert joiner_events[0].status_code == 201
    assert joiner_events[0].operation == "POST"


def test_mover_patches_user(engine, simple_scenario, mock_audit_logger):
    """El mover debe parchear el usuario y registrar un evento con phase='MOVER' y status 200."""
    engine.run_scenario(simple_scenario)
    events = mock_audit_logger.get_events()
    mover_events = [e for e in events if e.phase == "MOVER"]
    assert len(mover_events) == 1
    assert mover_events[0].status_code == 200
    assert mover_events[0].operation == "PATCH"
    assert mover_events[0].delta is not None and len(mover_events[0].delta) > 0


def test_leaver_deactivates_user(engine, simple_scenario, mock_audit_logger):
    """El leaver debe desactivar el usuario y registrar un evento con phase='LEAVER'."""
    engine.run_scenario(simple_scenario)
    events = mock_audit_logger.get_events()
    leaver_events = [e for e in events if e.phase == "LEAVER"]
    assert len(leaver_events) == 1
    assert leaver_events[0].operation == "PATCH"
    assert leaver_events[0].delta is not None
    assert leaver_events[0].delta.get("active") is False


def test_failed_event_recorded(engine, simple_scenario, mock_audit_logger):
    """Si el SCIM client falla, el evento debe registrarse con error y la simulación continúa."""
    with patch.object(engine.scim_client, "patch_user", side_effect=Exception("404 Not Found")):
        engine.run_scenario(simple_scenario)
    events = mock_audit_logger.get_events()
    mover_events = [e for e in events if e.phase == "MOVER"]
    assert len(mover_events) == 1
    assert mover_events[0].error is not None
    assert "404" in mover_events[0].error
    leaver_events = [e for e in events if e.phase == "LEAVER"]
    assert len(leaver_events) == 1


def test_audit_summary(engine, simple_scenario, mock_audit_logger):
    """get_summary() debe retornar los conteos correctos tras ejecutar el escenario."""
    engine.run_scenario(simple_scenario)
    summary = mock_audit_logger.get_summary()
    assert summary["total"] == 3
    assert summary["by_phase"]["JOINER"] == 1
    assert summary["by_phase"]["MOVER"] == 1
    assert summary["by_phase"]["LEAVER"] == 1
    assert summary["errors"] == 0
