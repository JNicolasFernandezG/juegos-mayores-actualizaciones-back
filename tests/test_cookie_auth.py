import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.core.security import create_access_token

@pytest.mark.asyncio
async def test_auth_via_cookie_and_logout():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Sin token ni cookie -> 401
        res = await client.get("/api/auth/session")
        assert res.status_code == 401

        # 2. Con cookie HttpOnly 'access_token'
        token = create_access_token({"id": 1, "tipo_usuario": 2, "name": "Operador Test", "email": "admin@test.com"})
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
        assert 'max-age=0' in cookie_header.lower() or 'expires=' in cookie_header.lower()
