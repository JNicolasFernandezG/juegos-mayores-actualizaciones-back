import pytest
from app.core.security import create_access_token

pytestmark = pytest.mark.asyncio


async def test_auth_via_cookie_and_logout(client, seeded_user):
    # 1. Sin token ni cookie -> 200 en modo invitado sin emitir 401 en consola
    res = await client.get("/api/auth/session")
    assert res.status_code == 200
    assert res.json() == {
        "success": True,
        "authenticated": False,
        "user": None,
        "racha": 0,
        "racha_ultima_fecha": None,
        "racha_hoy_ingresada": False,
    }

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

async def test_verificar_token_sets_httponly_cookie(client, monkeypatch, seeded_user):
    user = await seeded_user(tipo_usuario=1, name="Alumno Token")
    jwt_emitido = create_access_token(
        {"id": user["id"], "tipo_usuario": 1, "name": "Alumno Token", "email": user["email"]}
    )

    async def fake_verificar(req):
        return {
            "success": True,
            "valid": True,
            "token": jwt_emitido,
            "message": "Token verificado con éxito",
            "user": {"id": user["id"], "name": "Alumno Token", "email": user["email"], "tipoUsuario": 1},
        }

    monkeypatch.setattr("app.features.auth.router.verificar_token", fake_verificar)

    res = await client.post("/api/auth/verificar-token", json={"token": "token-externo"})
    assert res.status_code == 200
    cookie_header = res.headers.get("set-cookie", "")
    assert "access_token=" in cookie_header
    assert "httponly" in cookie_header.lower()


async def test_session_clears_invalid_cookie_without_401(client):
    client.cookies.set("access_token", "token-invalido-o-expirado")

    res = await client.get("/api/auth/session")
    assert res.status_code == 200
    data = res.json()
    assert data["authenticated"] is False
    assert data["user"] is None
    assert data["racha"] == 0

    cookie_header = res.headers.get("set-cookie", "")
    assert "access_token" in cookie_header
    assert "max-age=0" in cookie_header.lower() or "expires=" in cookie_header.lower()

    # Los endpoints privados sí siguen exigiendo autenticación con 401
    eco_res = await client.get("/api/economy/me")
    assert eco_res.status_code == 401
