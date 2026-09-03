"""Tests for 3D Developer Landing Page routing and static assets."""

def test_landing_page_served_at_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    text = response.text
    assert "ChatGPT × Antigravity" in text
    assert "canvas-3d" in text
    assert "landing.css" in text
    assert "landing.js" in text


def test_landing_page_alias(client):
    response = client.get("/landing")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "canvas-3d" in response.text


def test_dashboard_served_at_dashboard_route(client):
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    text = response.text
    assert "Command Center" in text
    assert "app.js" in text


def test_static_landing_assets(client):
    css_res = client.get("/static/landing.css")
    assert css_res.status_code == 200
    assert "canvas-3d-wrapper" in css_res.text

    js_res = client.get("/static/landing.js")
    assert js_res.status_code == 200
    assert "init3DVisualizer" in js_res.text
