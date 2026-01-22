from __future__ import annotations


def test_safe_next_path_blocks_open_redirect() -> None:
    from neuroleague_api.routers.auth import _safe_next_path

    assert _safe_next_path("https://evil.example.com/phish") == "/home"
    assert _safe_next_path("//evil.example.com/phish") == "/home"
    assert _safe_next_path("javascript:alert(1)") == "/home"
    assert _safe_next_path("home") == "/home"
    assert _safe_next_path("/home") == "/home"
    assert _safe_next_path("/replay/m_123") == "/replay/m_123"
    assert _safe_next_path("/home\nbad") == "/home"
