import pytest
from app.core.security import create_access_token

pytestmark = pytest.mark.asyncio


async def test_auth_via_cookie_and_logout(client, seeded_user):
    # 1. Sin token ni cookie -> 401
    res = await client.get("/api/auth/session")
    assert res.status_code == 401

    # 2. Con cookie HttpOnly 'access_token'
    user = await seeded_user(tipo_usuario=2, name="Operador Test")
    token = create_access_token(
        {"id": user["id"], "tipo_usuario": 2, "name": "Operador Test", "email": user["email"]}
    )
    client.cookies.set("access_token", token)
    res = await client.get("/api/auth/session")
    assert res.status_code == 200
    data = res.json()
    assert data["authenticated"] is True
    assert data["user"]["name"] == "Operador Test"

    # 3. Logout -> Borra cookie de sesión
    res_logout = await client.post("/api/auth/logout")
    assert res_logout.status_code == 200
    # Verificar que la cookie fue eliminada o expirada
    cookie_header = res_logout.headers.get("set-cookie", "")
    assert "access_token" in cookie_header
    assert "max-age=0" in cookie_header.lower() or "expires=" in cookie_header.lower()
