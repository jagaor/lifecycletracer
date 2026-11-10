import pytest
from fastapi.testclient import TestClient

from src.mock_server import app, store


@pytest.fixture(autouse=True)
# Limpia el store antes de cada test para garantizar aislamiento

def _reset_store():
    store.reset()
    yield
    store.reset()


@pytest.fixture
# Cliente de pruebas sobre la app FastAPI del mock SCIM

def client():
    return TestClient(app)


SCIM_USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"

def _payload(user_name="jdoe", email="jdoe@example.com"):
    return {
        "schemas": [SCIM_USER_SCHEMA],
        "userName": user_name,
        "name": {"givenName": "John", "familyName": "Doe"},
        "emails": [{"value": email, "primary": True}],
        "active": True,
    }


def test_create_user_201(client):
    resp = client.post("/scim/v2/Users", json=_payload())
    assert resp.status_code == 201
    body = resp.json()
    assert body["schemas"] == [SCIM_USER_SCHEMA]
    assert body["userName"] == "jdoe"
    assert "id" in body
    assert body["meta"]["resourceType"] == "User"
    assert "location" in body["meta"]


def test_create_duplicate_user_409(client):
    assert client.post("/scim/v2/Users", json=_payload()).status_code == 201
    resp = client.post("/scim/v2/Users", json=_payload())
    assert resp.status_code == 409
    body = resp.json()
    assert body["schemas"] == ["urn:ietf:params:scim:api:messages:2.0:Error"]
    assert body["status"] == "409"


def test_get_user_200(client):
    created = client.post("/scim/v2/Users", json=_payload()).json()
    resp = client.get(f"/scim/v2/Users/{created['id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == created["id"]
    assert body["userName"] == "jdoe"
    assert body["schemas"] == [SCIM_USER_SCHEMA]


def test_get_user_404(client):
    resp = client.get("/scim/v2/Users/no-existe")
    assert resp.status_code == 404
    body = resp.json()
    assert body["schemas"] == ["urn:ietf:params:scim:api:messages:2.0:Error"]
    assert body["status"] == "404"


def test_patch_user_replace_attribute(client):
    created = client.post("/scim/v2/Users", json=_payload()).json()
    patch = {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
        "Operations": [
            {"op": "replace", "path": "active", "value": False},
            {"op": "replace", "path": "name.givenName", "value": "Jane"},
        ],
    }
    resp = client.patch(f"/scim/v2/Users/{created['id']}", json=patch)
    assert resp.status_code == 200
    body = resp.json()
    assert body["active"] is False
    assert body["name"]["givenName"] == "Jane"
    assert body["id"] == created["id"]


def test_delete_user_204(client):
    created = client.post("/scim/v2/Users", json=_payload()).json()
    resp = client.delete(f"/scim/v2/Users/{created['id']}")
    assert resp.status_code == 204
    assert resp.content == b""
    assert client.get(f"/scim/v2/Users/{created['id']}").status_code == 404


def test_delete_nonexistent_user_404(client):
    resp = client.delete("/scim/v2/Users/no-existe")
    assert resp.status_code == 404
    body = resp.json()
    assert body["schemas"] == ["urn:ietf:params:scim:api:messages:2.0:Error"]
    assert body["status"] == "404"


def test_list_users_filter(client):
    client.post("/scim/v2/Users", json=_payload("alice", "alice@example.com"))
    client.post("/scim/v2/Users", json=_payload("bob", "bob@example.com"))
    resp = client.get('/scim/v2/Users', params={"filter": 'userName eq "alice"'})
    assert resp.status_code == 200
    body = resp.json()
    assert body["schemas"] == ["urn:ietf:params:scim:api:messages:2.0:ListResponse"]
    assert body["totalResults"] == 1
    assert body["Resources"][0]["userName"] == "alice"
