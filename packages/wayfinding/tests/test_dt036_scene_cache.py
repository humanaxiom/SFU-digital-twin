"""DT-036 immutable scene response cache contracts."""

import json
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.request import urlopen

import pytest

from wayfinding.demo import server as module


class FakeRepository:
    artifact_sha256 = "artifact-A"

    def __init__(self):
        self.calls = Counter()
        self.fail = set()
        self.entered = threading.Event()
        self.release = threading.Event()
        self.block = None
        self.catalog = ["A", "B"]

    def scene(self, level_id):
        self.calls[level_id] += 1
        if self.block == level_id:
            self.entered.set()
            assert self.release.wait(5), "test did not release blocked scene"
        if level_id in self.fail:
            raise module.ArtifactUnavailableError("synthetic failure")
        return {"crs": "EPSG:26910", "level": {"level_id": level_id},
                "units": [{"unit_id": "room", "geometry": {"type": "Point",
                           "coordinates": [123.125, 456.875]}}],
                "details": [], "landmarks": []}

    def provenance(self, layer):
        return {"layer": layer, "artifact_sha256": self.artifact_sha256}

    def levels(self):
        return [{"level_id": item} for item in self.catalog]


@pytest.fixture
def server():
    service = module.DemoHTTPServer(("127.0.0.1", 0), module.DemoRequestHandler)
    service.repository = FakeRepository()
    service.routing_service = None
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    try:
        yield service
    finally:
        service.repository.release.set()
        service.shutdown()
        service.server_close()
        thread.join(5)


def test_repeated_http_scene_builds_once_with_complete_identical_body(server):
    url = f"http://127.0.0.1:{server.server_port}/demo/v1/levels/A/scene"
    with urlopen(url, timeout=5) as response:
        first = response.read()
        assert response.headers["Content-Type"] == "application/json; charset=utf-8"
    with urlopen(url, timeout=5) as response:
        second = response.read()
    assert first == second
    expected_repository = FakeRepository()
    expected = expected_repository.scene("A")
    expected["limitations_id"] = module.LIMITATIONS_ID
    expected["provenance"] = [
        expected_repository.provenance(layer)
        for layer in ("level_26910", "unit_26910", "detail_26910", "landmark_26910")
    ]
    assert first == json.dumps(expected, separators=(",", ":"), ensure_ascii=True).encode()
    body = json.loads(first)
    assert body["limitations_id"] == module.LIMITATIONS_ID
    assert len(body["provenance"]) == 4
    assert body["units"][0]["geometry"]["coordinates"] == [123.125, 456.875]
    assert server.repository.calls["A"] == 1, "Repeated HTTP floor reads must reuse full bytes"


def test_concurrent_same_floor_is_deduplicated_and_warm_hit_does_not_wait(server):
    warm = server.scene_response("A")
    repository = server.repository
    repository.block = "B"
    with ThreadPoolExecutor(max_workers=4) as pool:
        cold = pool.submit(server.scene_response, "B")
        assert repository.entered.wait(2)
        duplicate = pool.submit(server.scene_response, "B")
        hit = pool.submit(server.scene_response, "A")
        try:
            assert hit.result(timeout=2) == warm, "Warm A must finish before blocked B releases"
            assert repository.calls["B"] == 1
        finally:
            repository.release.set()
        assert cold.result(timeout=2) == duplicate.result(timeout=2)
    assert repository.calls["B"] == 1
    assert not server.scene_pending


def test_cached_bytes_are_immutable_and_capture_one_repository(server):
    first = server.scene_response("A")
    decoded = json.loads(first)
    decoded["units"].clear()
    assert server.scene_response("A") == first
    assert len(json.loads(server.scene_response("A"))["units"]) == 1
    old = server.repository
    old.block = "B"
    new = FakeRepository()
    new.artifact_sha256 = "artifact-B"
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(server.scene_response, "B")
        assert old.entered.wait(2)
        server.repository = new
        old.release.set()
        body = json.loads(pending.result(timeout=2))
    assert all(item["artifact_sha256"] == "artifact-A" for item in body["provenance"])
    fresh = json.loads(server.scene_response("A"))
    assert all(item["artifact_sha256"] == "artifact-B" for item in fresh["provenance"])
    assert new.calls["A"] == 1
    assert ("artifact-A", "A") in server.scene_cache
    assert ("artifact-B", "A") in server.scene_cache


def test_lru_entry_limit_keeps_recent_hit_and_complete_evicted_floor(server, monkeypatch):
    monkeypatch.setattr(module, "MAX_SCENE_CACHE_ENTRIES", 2)
    first = server.scene_response("A")
    server.scene_response("B")
    assert server.scene_response("A") == first
    server.scene_response("C")
    assert list(server.scene_cache) == [("artifact-A", "A"), ("artifact-A", "C")]
    assert server.scene_response("B")
    assert server.repository.calls["B"] == 2
    assert len(server.scene_cache) == 2
    assert server.scene_cache_bytes == sum(map(len, server.scene_cache.values()))


def test_byte_bound_and_oversized_full_response_remain_available(server, monkeypatch):
    first = server.scene_response("A")
    monkeypatch.setattr(module, "MAX_SCENE_CACHE_BYTES", len(first))
    second = server.scene_response("B")
    assert len(second) == len(first)
    assert list(server.scene_cache) == [("artifact-A", "B")]
    assert server.scene_cache_bytes <= module.MAX_SCENE_CACHE_BYTES
    monkeypatch.setattr(module, "MAX_SCENE_CACHE_BYTES", 1)
    oversized = server.scene_response("C")
    assert json.loads(oversized)["units"][0]["geometry"]["coordinates"] == [123.125, 456.875]
    assert ("artifact-A", "C") not in server.scene_cache
    assert server.scene_response("C") == oversized
    assert server.repository.calls["C"] == 2


def test_failed_scene_is_not_cached_and_retries(server):
    server.repository.fail.add("A")
    with pytest.raises(module.ArtifactUnavailableError):
        server.scene_response("A")
    assert not server.scene_cache
    assert not server.scene_pending
    server.repository.fail.clear()
    assert json.loads(server.scene_response("A"))["level"]["level_id"] == "A"
    assert server.repository.calls["A"] == 2


def test_prewarm_preserves_lazy_creation_and_warms_successful_floors(server):
    assert not server.repository.calls, "Programmatic server construction stays lazy"
    assert server.warm_scene_cache() == 2
    assert server.scene_response("A")
    assert server.scene_response("B")
    assert server.repository.calls == {"A": 1, "B": 1}


@pytest.mark.parametrize("failure", ["scenes", "oversized", "catalog"])
def test_prewarm_is_best_effort_and_attempt_bounded(server, monkeypatch, capsys, failure):
    repository = server.repository
    repository.catalog = [f"L{index}" for index in range(25)]
    if failure == "scenes":
        repository.fail.update(repository.catalog)
    elif failure == "oversized":
        monkeypatch.setattr(module, "MAX_SCENE_CACHE_BYTES", 1)
    else:
        def broken_catalog():
            raise module.ArtifactUnavailableError("synthetic catalog failure")
        monkeypatch.setattr(repository, "levels", broken_catalog)
    server.warm_scene_cache()
    captured = capsys.readouterr()
    assert "synthetic" not in captured.out + captured.err
    assert sum(repository.calls.values()) <= 16
    if failure != "catalog":
        assert sum(repository.calls.values()) == 16
    assert not server.scene_cache
    assert not server.scene_pending
    repository.fail.clear()
    assert server.scene_response("foreground")
