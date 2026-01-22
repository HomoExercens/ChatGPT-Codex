from __future__ import annotations


def test_public_base_url_overrides_og_urls(monkeypatch, seeded_db) -> None:
    monkeypatch.setenv("NEUROLEAGUE_PUBLIC_BASE_URL", "https://neuroleague.example.com")

    from fastapi.testclient import TestClient

    from neuroleague_api.main import create_app

    client = TestClient(create_app())
    resp = client.get("/s/clip/r_test_seed?start=0&end=1")
    assert resp.status_code == 200
    html = resp.text
    assert 'property="og:url"' in html
    assert "https://neuroleague.example.com/s/clip/r_test_seed" in html
    assert "https://neuroleague.example.com/s/clip/r_test_seed/thumb.png" in html
