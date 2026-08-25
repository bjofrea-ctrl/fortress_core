"""
Regresión del INVARIANTE de superficie de escritura (Brecha 5, handover §6.2):
TODO endpoint no-GET (POST/PUT/DELETE/PATCH) de la API debe depender de
verify_api_key (hmac.compare_digest contra settings.SECRET_KEY).

Estado verificado contra el código real (2026-08-24): los únicos endpoints de
escritura son los 2 POST de governance, ambos con auth desde el cierre P0 del
2026-08-12. Este test fija el invariante hacia adelante: si alguien agrega un
endpoint de escritura sin la dependencia verify_api_key, la suite FALLA aquí.

Convención del repo (ver test_costs_api.py): NO hay httpx/TestClient en
dev-deps — el chequeo es estructural sobre el árbol de dependencias FastAPI.

Los endpoints de lectura pública NO se tocan (decisión de producto: UI pública).
"""
from app.main import app
from fastapi.routing import APIRoute


def _write_routes():
    """Rutas de escritura registradas en la app (métodos sin GET)."""
    return [
        r
        for r in app.routes
        if isinstance(r, APIRoute) and "GET" not in r.methods
    ]


def _dependency_calls(dependant):
    """Nombres de todos los callables en el árbol de dependencias (recursivo)."""
    calls = []
    for dep in dependant.dependencies:
        calls.append(dep.call)
        calls.extend(_dependency_calls(dep))
    return calls


def _has_verify_api_key(route):

    from app.api.routes.governance import verify_api_key

    return any(call is verify_api_key for call in _dependency_calls(route.dependant))


def test_write_inventory_is_known():
    """El inventario de escritura es el conocido: 2 POST de governance con auth.
    Si este test falla porque CRECIÓ la superficie, verificar que las rutas
    nuevas tengan verify_api_key antes de actualizar este número."""
    routes = _write_routes()
    resumen = [f"{sorted(r.methods)} {r.path}" for r in routes]
    assert len(routes) == 2, f"superficie de escritura cambió: {resumen}"


def test_all_write_endpoints_have_verify_api_key():
    """INVARIANTE Brecha 5: ninguna ruta de escritura sin verify_api_key."""
    sin_auth = [r.path for r in _write_routes() if not _has_verify_api_key(r)]
    assert not sin_auth, (
        f"endpoints de ESCRITURA sin auth (requieren verify_api_key): {sin_auth}"
    )


def test_verify_api_key_is_the_shared_mechanism():
    """El mecanismo es EL del proyecto (governance.verify_api_key), no otro."""
    import inspect

    from app.api.routes.governance import verify_api_key

    src = inspect.getsource(verify_api_key)
    assert "hmac.compare_digest" in src
    assert "settings.SECRET_KEY" in src

