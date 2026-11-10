import httpx
import pytest
from src.scim_client import SCIMClient

BASE_URL = "http://testserver/scim/v2"


def _client_with_transport(handler):
    transport = httpx.MockTransport(handler)
    return SCIMClient(base_url=BASE_URL, transport=transport)


@pytest.mark.asyncio
async def test_create_user_returns_201():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/scim/v2/Users"
        payload = request.read()
        assert b'"userName"' in payload
        return httpx.Response(201, json={"id": "user-1", "userName": "jdoe"})

    client = _client_with_transport(handler)
    status, body = await client.create_user({"userName": "jdoe", "active": True})
    assert status == 201
    assert body["id"] == "user-1"


@pytest.mark.asyncio
async def test_patch_user_returns_200():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PATCH"
        assert request.url.path == "/scim/v2/Users/user-1"
        return httpx.Response(200, json={"id": "user-1", "active": False})

    client = _client_with_transport(handler)
    status, body = await client.patch_user("user-1", {"Operations": []})
    assert status == 200
    assert body["active"] is False


@pytest.mark.asyncio
async def test_delete_user_returns_204():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        assert request.url.path == "/scim/v2/Users/user-1"
        return httpx.Response(204)

    client = _client_with_transport(handler)
    status, body = await client.delete_user("user-1")
    assert status == 204
    assert body is None


@pytest.mark.asyncio
async def test_deactivate_user_sets_active_false():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.read()
        return httpx.Response(200, json={"id": "user-1", "active": False})

    client = _client_with_transport(handler)
    await client.deactivate_user("user-1")
    assert b'"op": "replace"' in captured["body"]
    assert b'"path": "active"' in captured["body"]
    assert b'false' in captured["body"]


@pytest.mark.asyncio
async def test_http_error_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    client = _client_with_transport(handler)
    with pytest.raises(httpx.HTTPStatusError):
        await client.create_user({"userName": "jdoe"})
