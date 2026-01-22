from __future__ import annotations

from urllib.parse import parse_qs, urlparse


def test_clip_share_url_endpoint_mints_variant_and_range(api_client) -> None:
    login = api_client.post("/api/auth/login", json={"username": "demo"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r1 = api_client.get(
        "/api/clips/r_test_seed/share_url?orientation=vertical", headers=headers
    )
    assert r1.status_code == 200
    data1 = r1.json()

    assert data1["variant"] in {"10s", "12s", "15s"}
    assert isinstance(data1.get("start_sec"), (int, float))
    assert isinstance(data1.get("end_sec"), (int, float))
    assert data1.get("captions_version")
    assert data1.get("share_url_vertical")
    assert data1.get("captions_template_id") in {"A", "B", "C"}

    max_dur = {"10s": 10.0, "12s": 12.0, "15s": 15.0}[data1["variant"]]
    assert (float(data1["end_sec"]) - float(data1["start_sec"])) <= (max_dur + 1e-6)

    u = urlparse(str(data1["share_url_vertical"]))
    assert u.path == "/s/clip/r_test_seed"
    q = parse_qs(u.query)
    assert q.get("v") == ["1"]
    assert q.get("lenv") == [data1["variant"]]
    assert q.get("cv") == [data1["captions_version"]]
    assert q.get("start") == [f"{float(data1['start_sec']):.1f}"]
    assert q.get("end") == [f"{float(data1['end_sec']):.1f}"]
    assert q.get("ctpl") == [data1["captions_template_id"]]

    r2 = api_client.get(
        "/api/clips/r_test_seed/share_url?orientation=vertical", headers=headers
    )
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["variant"] == data1["variant"]
    assert float(data2["start_sec"]) == float(data1["start_sec"])
    assert float(data2["end_sec"]) == float(data1["end_sec"])
