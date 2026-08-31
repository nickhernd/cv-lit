"""Tests de la pantalla de Configuración (GET/PUT /api/settings,
POST /api/settings/test-connection) — añadidos en 2026-08-31 junto con la
propia función: cada usuario de la app instalada guarda sus credenciales de
Obscape aquí en vez de en un .env que no existe en el ejecutable distribuido.

No mockea la llamada real a Obscape en el caso de credenciales inválidas
(usa una clave claramente falsa contra el servidor real) — es justo lo que
hace falta probar: que un fallo de autenticación se propaga como error y no
se traga en silencio (ver el comentario en test_obscape_connection() sobre
por qué NO se usa list_stations() ahí).
"""

import sys
import os
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="cvlit_test_settings_data_")
_TMP_CALIB_DIR = tempfile.mkdtemp(prefix="cvlit_test_settings_calib_")
os.environ["CVLIT_DATA_DIR"] = _TMP_DATA_DIR
os.environ["CVLIT_CALIBRATION_DIR"] = _TMP_CALIB_DIR
os.environ.setdefault("APP_MODE", "real")

from fastapi.testclient import TestClient

import config
import main

client = TestClient(main.app)


def _clear_settings():
    p = Path(config.CALIBRATION_DIR) / "app_settings.json"
    if p.exists():
        p.unlink()


def test_get_settings_defaults_to_unconfigured():
    _clear_settings()
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is False
    assert data["obscape_username"] is None


def test_put_settings_persists_and_reports_configured():
    _clear_settings()
    resp = client.put("/api/settings", json={
        "obscape_username": "user_test",
        "obscape_api_key": "key_test_123",
    })
    assert resp.status_code == 200
    assert resp.json()["configured"] is True

    resp2 = client.get("/api/settings")
    data = resp2.json()
    assert data["obscape_username"] == "user_test"
    assert data["obscape_api_key"] == "key_test_123"
    assert data["configured"] is True

    _clear_settings()


def test_put_settings_partial_update_keeps_other_field():
    _clear_settings()
    client.put("/api/settings", json={"obscape_username": "user_a"})
    client.put("/api/settings", json={"obscape_api_key": "key_b"})

    data = client.get("/api/settings").json()
    assert data["obscape_username"] == "user_a"
    assert data["obscape_api_key"] == "key_b"

    _clear_settings()


def test_settings_file_written_under_calibration_dir():
    _clear_settings()
    client.put("/api/settings", json={"obscape_username": "u", "obscape_api_key": "k"})
    path = Path(config.CALIBRATION_DIR) / "app_settings.json"
    assert path.exists()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved == {"obscape_username": "u", "obscape_api_key": "k"}
    _clear_settings()


def test_connection_without_credentials_reports_error_not_success(monkeypatch):
    """El caso real que motivó reescribir este endpoint: list_stations() se
    traga cualquier fallo (red, credenciales inválidas) y devuelve [] — con
    eso, un typo en la clave habría dado "Conexión correcta" igualmente. No
    se prueba aquí contra el servidor real de Obscape (evita depender de red
    para que este archivo corra offline como el resto de tests): sin
    credenciales guardadas, ObscapeClient() ya lanza RuntimeError por sí solo,
    que es exactamente el tipo de fallo que antes se habría tragado en
    silencio si el endpoint hubiera seguido usando list_stations().

    Hay que limpiar también OBSCAPE_USERNAME/OBSCAPE_API_KEY del entorno: la
    primera vez que se importa obscape_api en este proceso carga el .env real
    de la raíz del repo (con setdefault, así que solo pasa una vez) — se
    fuerza ese import aquí primero y LUEGO se limpia el entorno, para que el
    fallback del .env real no enmascare el caso "sin credenciales" que se
    quiere probar."""
    _clear_settings()
    sys.path.insert(0, str(ROOT / "acces_api"))
    import obscape_api  # dispara _load_dotenv() una sola vez, antes de limpiar
    monkeypatch.delenv("OBSCAPE_USERNAME", raising=False)
    monkeypatch.delenv("OBSCAPE_API_KEY", raising=False)

    resp = client.post("/api/settings/test-connection")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"
    assert "credenciales" in data["detail"].lower()
