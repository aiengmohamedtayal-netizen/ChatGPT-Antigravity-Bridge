"""Tests for headless root endpoint and metadata routing."""


def test_headless_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["mode"] == "headless"
    assert "ChatGPT" in data["app"]
    assert "chatgpt_schema" in data
    assert "mcp_endpoint" in data


def test_health_check_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
