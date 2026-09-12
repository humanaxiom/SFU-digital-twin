"""Failure boundaries for isolated builds, independent of private GIS inputs."""

import json
import pickle

import networkx as nx
import pytest

from wayfinding.etl import rebuild


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    root = tmp_path / "experiments"
    root.mkdir()
    source = tmp_path / "legacy.gdb"
    source.mkdir()
    (source / "fixture").write_bytes(b"source")
    monkeypatch.setattr(rebuild, "EXPERIMENTS_ROOT", root)
    monkeypatch.setattr(rebuild, "SOURCE_PATH", source)
    monkeypatch.setattr(
        rebuild, "LEGACY_SHA256", rebuild.hash_directory(source)["sha256"]
    )
    monkeypatch.setattr(rebuild, "runtime_identity", lambda: {"image_id": "test-image"})

    def extract(gdb_path, gpkg_path, overwrite=False):
        assert not overwrite
        gpkg_path.write_bytes(b"raw extraction")
        return {"Units_26910": 2}

    monkeypatch.setattr(rebuild, "extract_to_gpkg", extract)
    return root, source


@pytest.mark.parametrize("name", ["../escape", "/absolute", "a/b", "a\\b", ".", "..", "", "é"])
def test_run_id_cannot_escape(sandbox, name):
    with pytest.raises(ValueError, match="run ID"):
        rebuild.extract_run(name)
    assert not list(sandbox[0].iterdir())


def test_extraction_preserves_raw_and_refuses_reuse(sandbox):
    run = rebuild.extract_run("first")
    raw = run / "raw/wayfinding.gpkg"
    assert raw.read_bytes() == b"raw extraction"
    manifest = json.loads((run / "run.json").read_text())
    assert manifest["state"] == "extracted"
    assert manifest["path_base"] == "run_directory"
    assert manifest["source"]["sha256"] == rebuild.LEGACY_SHA256
    with pytest.raises(FileExistsError):
        rebuild.extract_run("first")
    assert raw.read_bytes() == b"raw extraction"


def test_unknown_source_fails_before_creating_run(sandbox):
    (sandbox[1] / "fixture").write_bytes(b"changed")
    with pytest.raises(ValueError, match="source snapshot"):
        rebuild.extract_run("unknown")
    assert not (sandbox[0] / "unknown").exists()


def test_raw_tamper_blocks_derivation_before_processing(sandbox, monkeypatch):
    run = rebuild.extract_run("tampered")
    (run / "raw/wayfinding.gpkg").write_bytes(b"corruption")
    with pytest.raises(ValueError, match="hash mismatch"):
        rebuild.derive_run("tampered")
    assert not (run / "derived").exists()


def test_run_symlink_is_rejected(sandbox, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (sandbox[0] / "alias").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        rebuild.extract_run("alias")
    assert not list(outside.iterdir())


def test_artifact_symlink_is_rejected_before_read(sandbox, tmp_path):
    run = rebuild.extract_run("linked")
    target = tmp_path / "other"
    target.write_bytes(b"raw extraction")
    raw = run / "raw/wayfinding.gpkg"
    raw.unlink()
    raw.symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        rebuild.derive_run("linked")


def test_extraction_failure_is_incomplete_and_not_reusable(sandbox, monkeypatch):
    def fail(**kwargs):
        kwargs["gpkg_path"].write_bytes(b"partial")
        raise RuntimeError("fixture failure")

    monkeypatch.setattr(rebuild, "extract_to_gpkg", fail)
    with pytest.raises(RuntimeError, match="fixture failure"):
        rebuild.extract_run("failed")
    manifest = json.loads((sandbox[0] / "failed/run.json").read_text())
    assert manifest["state"] == "failed"
    with pytest.raises(ValueError, match="state"):
        rebuild.derive_run("failed")
    with pytest.raises(FileExistsError):
        rebuild.extract_run("failed")


def test_toolchain_drift_blocks_later_stage(sandbox, monkeypatch):
    rebuild.extract_run("drift")
    monkeypatch.setattr(rebuild, "runtime_identity", lambda: {"image_id": "other"})
    with pytest.raises(ValueError, match="toolchain"):
        rebuild.derive_run("drift")


def test_manifest_paths_and_stage_ledger_are_checked(sandbox):
    run = rebuild.extract_run("manifest")
    path = run / "run.json"
    document = json.loads(path.read_text())
    document["stages"][0]["outputs"] = {"../outside": "0" * 64}
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="Manifest hash mismatch"):
        rebuild.derive_run("manifest")


def test_finalize_requires_completed_derivation(sandbox):
    rebuild.extract_run("early")
    with pytest.raises(ValueError, match="state"):
        rebuild.finalize_run("early")


def test_compare_requires_distinct_complete_runs(sandbox):
    rebuild.extract_run("one")
    with pytest.raises(ValueError, match="distinct runs"):
        rebuild.compare_runs("one", "one")


def test_experiments_root_symlink_is_rejected(sandbox, monkeypatch, tmp_path):
    alias = tmp_path / "alias-root"
    alias.symlink_to(sandbox[0], target_is_directory=True)
    monkeypatch.setattr(rebuild, "EXPERIMENTS_ROOT", alias)
    with pytest.raises(ValueError, match="symlink"):
        rebuild.extract_run("rooted")


@pytest.fixture
def tiny_pipeline(sandbox, monkeypatch):
    """Exercise real stage/ledger/files with inexpensive stand-ins for GIS stages."""
    for name in ("facilities", "levels", "units", "landmarks"):
        monkeypatch.setattr(rebuild.normalise, f"normalise_{name}", lambda *args: 0)
    monkeypatch.setattr(rebuild.normalise, "normalise_details", lambda path: {"detail": 0})
    monkeypatch.setattr(rebuild, "_units_from_gpkg", lambda path: [])

    def raw(path):
        (path / "graph_raw.pkl").write_bytes(pickle.dumps(nx.MultiDiGraph()))
        (path / "node_map.pkl").write_bytes(pickle.dumps({}))
        (path / "graph_raw_stats.json").write_text("{}")
        return 0

    def transitions(path):
        (path / "graph_with_transitions.pkl").write_bytes((path / "graph_raw.pkl").read_bytes())
        (path / "graph_with_transitions_stats.json").write_text("{}")
        return 0

    def contract(path):
        (path / "graph_contracted.pkl").write_bytes((path / "graph_raw.pkl").read_bytes())
        stats = {"lineage": {
            "inputs": [{"path": f"derived/{name}", "sha256": rebuild._sha(path / name)}
                       for name in ("graph_with_transitions.pkl", "wayfinding.gpkg")],
            "outputs": [{"path": "derived/graph_contracted.pkl",
                         "sha256": rebuild._sha(path / "graph_contracted.pkl")}],
        }}
        (path / "graph_contracted_stats.json").write_text(json.dumps(stats))
        return 0

    monkeypatch.setattr(rebuild.graph, "run_graph_raw", raw)
    monkeypatch.setattr(rebuild.graph, "run_graph_transitions", transitions)
    monkeypatch.setattr(rebuild.graph, "run_graph_contract", contract)
    return sandbox


def test_complete_staged_build_and_comparison(tiny_pipeline):
    for name in ("left", "right"):
        run = rebuild.extract_run(name)
        rebuild.derive_run(name)
        rebuild.finalize_run(name)
        manifest = json.loads((run / "run.json").read_text())
        assert manifest["state"] == "complete"
        assert manifest["source_reverified"] is True
        assert len(manifest["stages"]) == 6
        assert (run / rebuild.RAW).read_bytes() == b"raw extraction"
    result = rebuild.compare_runs("left", "right")
    assert result["equivalent"]
    assert result["source_equal"]
    assert result["promotion"] == "not_promoted"
    assert (tiny_pipeline[0] / "comparisons/left--right.json").exists()
    with pytest.raises(FileExistsError):
        rebuild.compare_runs("left", "right")


def test_graph_failure_stops_pipeline_and_finalization(tiny_pipeline, monkeypatch):
    run = rebuild.extract_run("broken")
    monkeypatch.setattr(rebuild.graph, "run_graph_raw", lambda path: 7)
    with pytest.raises(RuntimeError, match="exit 7"):
        rebuild.derive_run("broken")
    manifest = json.loads((run / "run.json").read_text())
    assert manifest["state"] == "failed"
    assert [stage["name"] for stage in manifest["stages"]] == ["extract", "normalise"]
    assert not (run / rebuild.TRANSITIONS).exists()
    with pytest.raises(ValueError, match="state"):
        rebuild.finalize_run("broken")


def test_source_drift_prevents_completed_state(tiny_pipeline):
    run = rebuild.extract_run("drift-final")
    rebuild.derive_run("drift-final")
    (tiny_pipeline[1] / "fixture").write_bytes(b"source changed")
    with pytest.raises(ValueError, match="Source changed"):
        rebuild.finalize_run("drift-final")
    assert json.loads((run / "run.json").read_text())["state"] == "failed"


def test_artifact_tamper_prevents_finalization(tiny_pipeline):
    run = rebuild.extract_run("changed-final")
    rebuild.derive_run("changed-final")
    (run / rebuild.CONTRACTED).write_bytes(b"untrusted pickle must not be loaded")
    with pytest.raises(ValueError, match="Artifact hash mismatch"):
        rebuild.finalize_run("changed-final")
    assert json.loads((run / "run.json").read_text())["state"] == "derived"


def test_consumed_input_cannot_be_modified_by_stage(tiny_pipeline, monkeypatch):
    run = rebuild.extract_run("mutation")

    def mutate(path):
        (path / "wayfinding.gpkg").write_bytes(b"unexpected write")
        return 0

    monkeypatch.setattr(rebuild.graph, "run_graph_raw", mutate)
    with pytest.raises(ValueError, match="Input changed"):
        rebuild.derive_run("mutation")
    assert json.loads((run / "run.json").read_text())["state"] == "failed"


def test_output_path_escape_is_rejected(sandbox):
    with pytest.raises(ValueError, match="escapes"):
        rebuild._file(sandbox[0], "../outside")


def test_cli_failure_propagates_without_build(sandbox, capsys):
    assert rebuild.main(["extract", "--run-id", "../unsafe"]) == 1
    assert "Invalid run ID" in capsys.readouterr().err
