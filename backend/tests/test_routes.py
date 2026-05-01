from fastapi.testclient import TestClient

from app.api.routes import get_chat_log_repository, get_dialogue_service
from app.main import app


def test_cached_route_dependencies_are_hash_safe() -> None:
    client = TestClient(app)

    catalog_response = client.get("/api/admin/catalog/summary")
    assert catalog_response.status_code == 200
    assert catalog_response.json()["product_count"] > 0

    mappings_response = client.get("/api/admin/mappings")
    assert mappings_response.status_code == 200

    logs_response = client.get("/api/admin/chat-logs")
    assert logs_response.status_code == 200


def test_stream_chat_route_returns_done_event_without_llm(monkeypatch) -> None:
    service = get_dialogue_service()
    monkeypatch.setattr(service.longcat_client.settings, "longcat_api_key", "")
    client = TestClient(app)

    with client.stream(
        "POST",
        "/api/chat/stream",
        json={
            "session_id": "route-stream-smoke",
            "text": "你好",
            "response_mode": "cards",
        },
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "event: status" in body
    assert "event: done" in body
    assert "GENERAL_REPLY" not in body


def test_stream_chat_route_does_not_fallback_when_chat_log_write_fails(monkeypatch) -> None:
    service = get_dialogue_service()
    monkeypatch.setattr(service.longcat_client.settings, "longcat_api_key", "")

    class FailingChatLogRepository:
        def append_log(self, **kwargs):
            raise OSError("log file is temporarily unavailable")

    app.dependency_overrides[get_chat_log_repository] = lambda: FailingChatLogRepository()
    client = TestClient(app)
    try:
        with client.stream(
            "POST",
            "/api/chat/stream",
            json={
                "session_id": "route-stream-log-failure",
                "text": "你好",
                "response_mode": "cards",
            },
        ) as response:
            body = "".join(response.iter_text())
    finally:
        app.dependency_overrides.pop(get_chat_log_repository, None)

    assert response.status_code == 200
    assert "event: done" in body
    assert "stream_fallback" not in body
    assert "商品卡片没有完整返回" not in body
