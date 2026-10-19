import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from sqlalchemy.exc import OperationalError

from app.core.config import get_settings
from app.services import weather_service
from app.services.weather_ingestion import fetch, run_once


def test_feed_http_contract_and_source_identity():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.headers["Authorization"] == "Bearer test-feed-token"
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps([{
                "location_id": 1, "observed_at": "2025-01-01T00:00:00Z",
                "source": "untrusted", "source_type": "provider", "temperature_c": 25,
            }]).encode())
        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    from pydantic import SecretStr
    settings = get_settings().model_copy(update={
        "weather_feed_url": f"http://127.0.0.1:{server.server_port}",
        "weather_feed_source": "local-synthetic-test", "weather_feed_token": SecretStr("test-feed-token"),
    })
    try:
        rows = fetch(settings)
        assert rows[0].source_type == "synthetic"
        assert rows[0].source == "local-synthetic-test"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_disabled_worker_never_fetches():
    def fail(_):
        raise AssertionError("disabled worker fetched data")
    assert run_once(get_settings(), fetcher=fail) == {"status": "disabled"}


def test_database_failure_is_safe(client, monkeypatch):
    def fail(*args, **kwargs):
        raise OperationalError("secret statement", {}, Exception("secret password"))
    monkeypatch.setattr(weather_service, "observations", fail)
    response = client.get("/api/weather/latest?location_id=1")
    assert response.status_code == 503
    assert "secret" not in response.text
