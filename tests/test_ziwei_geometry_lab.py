"""本地实验接口、实际坐标框架与种子归属歧义验收。"""

import http.client
import json
import math
import threading
from datetime import datetime, timezone
from urllib.parse import urlencode

import numpy as np
import pytest

from tools import ziwei_geometry_lab as lab_module
from tools.ziwei_geometry_lab import GeometryLab, nearest_seed, parse_parameters, unit_vector


def test_nearest_seed_preserves_coincident_label_conflict_and_wraps_ra_seam():
    seeds = [{"vector": [1, 0, 0], "branch": "子"}, {"vector": [1, 0, 0], "branch": "午"}]
    conflict = nearest_seed([1, 0, 0], seeds)
    assert conflict["ambiguous"] and conflict["branch"] is None
    assert set(conflict["candidate_branches"]) == {"子", "午"}
    seam = [
        {"vector": unit_vector(359, 0), "branch": "子"},
        {"vector": unit_vector(10, 0), "branch": "丑"},
    ]
    result = nearest_seed(unit_vector(1, 0), seam)
    assert result["branch"] == "子" and result["distance_deg"] == pytest.approx(2)
    tied = nearest_seed(
        unit_vector(0, 0),
        [
            {"vector": unit_vector(359, 0), "branch": "子"},
            {"vector": unit_vector(1, 0), "branch": "丑"},
        ],
    )
    assert tied["ambiguous"]


def test_seed_assignment_is_rotation_invariant():
    angle = math.radians(73)
    rotation = np.array(
        [[math.cos(angle), -math.sin(angle), 0], [math.sin(angle), math.cos(angle), 0], [0, 0, 1]]
    )
    point = unit_vector(30, 20)
    seeds = [
        {"vector": unit_vector(20, 15), "branch": "子"},
        {"vector": unit_vector(130, -10), "branch": "丑"},
    ]
    before = nearest_seed(point, seeds)
    after = nearest_seed(
        (rotation @ point).tolist(),
        [{**seed, "vector": (rotation @ seed["vector"]).tolist()} for seed in seeds],
    )
    assert before["branch"] == after["branch"]
    assert before["distance_deg"] == pytest.approx(after["distance_deg"], abs=1e-12)


def test_active_boundary_ignores_occluded_pairs_and_merges_same_palace():
    seeds = [
        {"vector": [1, 0, 0], "branch": "子"},
        {"vector": [-1, 0, 0], "branch": "午"},
    ]
    assert nearest_seed([0, 1, 0], seeds)["ambiguous"]
    third = {"vector": [0, 1, 0], "branch": "卯"}
    assert nearest_seed([0, 1, 0], [*seeds, third])["branch"] == "卯"
    assert not nearest_seed([0, 1, 0], [{**s, "branch": "子"} for s in seeds])["ambiguous"]
    pole_seeds = [
        {"vector": unit_vector(0, 80), "branch": "子"},
        {"vector": unit_vector(180, 10), "branch": "午"},
    ]
    assert {nearest_seed(unit_vector(a, 90), pole_seeds)["branch"] for a in range(0, 360, 30)} == {
        "子"
    }


@pytest.mark.parametrize(
    "parameters",
    [
        {"epoch": "2026-10-12T20:00:00"},
        {"epoch": "1899-12-31T12:00:00Z"},
        {"epoch": "2101-01-01T12:00:00Z"},
        {"lat": "nan"},
        {"lon": "inf"},
        {"lat": "90.1"},
        {"lon": "180.1"},
        {"tz": "UTC+08:00"},
        {"tz": "../secret"},
        {"path": "main.py"},
        {"epoch": ""},
    ],
)
def test_invalid_parameters_are_rejected_before_compute(parameters):
    with pytest.raises(ValueError):
        parse_parameters(parameters)


def test_default_now_and_explicit_offset_are_normalized():
    now = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)
    moment, site = parse_parameters({}, now)
    assert moment == now and site["timezone"] == "Asia/Shanghai"
    assert site["latitude"] == 39.9075 and site["longitude"] == 116.39723
    explicit, _ = parse_parameters({"epoch": "2026-10-12T20:00:00+08:00"})
    assert explicit == now


def test_real_state_vectors_have_consistent_frames_and_public_provenance():
    lab = GeometryLab()
    try:
        state = lab.state({"epoch": "2026-10-12T20:00:00+08:00"})
        assert state["epoch_utc"].startswith("2026-10-12T12:00:00")
        assert state["epoch_local"].startswith("2026-10-12T20:00:00")
        assert len(state["rows"]) == 17
        seeds = [
            {"vector": r["unit_vector"], "branch": r["traditional_branch"]} for r in state["rows"]
        ]
        for row in state["rows"]:
            assert nearest_seed(row["unit_vector"], seeds)["branch"] == row["traditional_branch"]
        transform = np.array(state["frames"]["equatorial_to_horizontal"])
        assert transform @ transform.T == pytest.approx(np.eye(3), abs=1e-12)
        for row in state["rows"]:
            assert np.linalg.norm(row["unit_vector"]) == pytest.approx(1)
            assert transform @ row["unit_vector"] == pytest.approx(
                row["vector_horizontal"], abs=1e-12
            )
            assert "traditional_branch" in row and "mapping" in row
            assert "research_branch" not in row
        assert len(state["provenance"]["ephemeris"]["sha256"]) == 64
        assert len(state["provenance"]["star_catalog"]["sha256"]) == 64
        assert state["provenance"]["code_version"] == lab_module.PROFILE
    finally:
        lab.close()
        lab.close()
    with pytest.raises(RuntimeError, match="关闭"):
        lab.state({})


def test_http_exact_routes_validation_and_server_owned_cleanup(monkeypatch, tmp_path, capsys):
    page = tmp_path / "ziwei_geometry_lab.html"
    page.write_text("<!doctype html><title>local test</title>", encoding="utf-8")
    monkeypatch.setattr(lab_module, "PAGE_PATH", page)
    server = lab_module.create_server(0)
    assert server.server_address[0] == "127.0.0.1"
    port = server.server_address[1]
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, name="ziwei-lab-test"
    )
    thread.start()

    def get(path):
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            return response.status, response.getheaders(), response.read()
        finally:
            connection.close()

    try:
        status, headers, body = get("/")
        assert status == 200 and body == page.read_bytes()
        assert ("Cache-Control", "no-store") in headers
        for route, (path, _) in lab_module.FONT_FILES.items():
            assert get(route)[2] == path.read_bytes()
        status, _, body = get("/api/state?" + urlencode({"epoch": "2026-10-12T20:00:00+08:00"}))
        assert status == 200 and len(json.loads(body)["rows"]) == 17
        assert get("/api/state?lat=nan")[0] == 400
        assert get("/api/state?lat=0&lat=1")[0] == 400
        assert get("/fonts/../main.py")[0] == 404
        assert get("/fonts/%2e%2e/main.py")[0] == 404
        assert get("/main.py")[0] == 404
        assert list(tmp_path.iterdir()) == [page]
        assert not capsys.readouterr().err
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    assert not thread.is_alive() and server.lab._closed and server.socket.fileno() == -1
