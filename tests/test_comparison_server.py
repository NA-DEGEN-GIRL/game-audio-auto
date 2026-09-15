import importlib.util
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest


@pytest.fixture
def player(tmp_path):
    spec = importlib.util.spec_from_file_location("player", Path(__file__).parents[1] / "scripts/serve_comparison.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("Player", encoding="utf-8")
    deliveries = tmp_path / "deliveries"
    deliveries.mkdir()
    (deliveries / "sample.wav").write_bytes(b"RIFF0123456789")
    (tmp_path / "secret.wav").write_bytes(b"private")
    catalog = deliveries / "catalog.json"
    catalog.write_text(json.dumps({"tracks": [
        {"id": "good", "original": "sample.wav"},
        {"id": "escape", "original": "../secret.wav"}]}), encoding="utf-8")
    server = ThreadingHTTPServer(("127.0.0.1", 0), module.make_handler(web, deliveries, catalog))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    with httpx.Client(base_url=f"http://127.0.0.1:{server.server_port}") as client:
        yield client
    server.shutdown()
    server.server_close()
    thread.join()


def test_audio_range_and_head_for_browser_seeking(player):
    response = player.get("/audio/good/original", headers={"Range": "bytes=4-7"})
    assert response.status_code == 206
    assert response.content == b"0123"
    assert response.headers["Content-Range"] == "bytes 4-7/14"
    assert player.get("/audio/good/original", headers={"Range": "bytes=-3"}).content == b"789"
    assert player.get("/audio/good/original", headers={"Range": "bytes=999-"}).status_code == 416
    response = player.head("/audio/good/original")
    assert response.status_code == 200 and not response.content
    assert response.headers["Content-Length"] == "14"


def test_only_catalog_audio_can_be_read_and_no_disk_paths_leak(player):
    assert player.get("/audio/escape/original").status_code == 404
    assert player.get("/audio/missing/original").status_code == 404
    assert player.get("/.secrets/hf_token").status_code == 404
    assert player.get("/api/catalog", headers={"Host": "external.example"}).status_code == 403
    assert player.post("/api/catalog", json={}).status_code == 501
    data = player.get("/api/catalog").json()
    assert data["tracks"][0]["original"] == "/audio/good/original"
    assert "secret.wav" not in json.dumps(data)
