"""HTTP API tests.

The pipeline runner is dependency-injected, so the default suite never calls
the real LLM/vision backends or cadquery: a fake runner writes tiny placeholder
artifacts and sets a chosen terminal status. One opt-in integration test
(``integration`` marker + ``API_INTEGRATION=1``) exercises the real CLI.
"""

import os
from concurrent.futures import Future
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.jobs import (
    ARTIFACT_SPECS,
    DOWNLOADABLE,
    FAILED,
    OUTPUT_BASE,
    RUNNING,
    SUCCEEDED,
    UNVALIDATED,
    Job,
    JobStore,
    collect_artifacts,
    sweep_expired,
)

PDF_BYTES = b"%PDF-1.4\n%fake datasheet\n"


class SyncExecutor:
    """Runs submitted work inline so tests are deterministic (no threads)."""

    def submit(self, fn, *args, **kwargs):
        fut: Future = Future()
        try:
            fut.set_result(fn(*args, **kwargs))
        except Exception as exc:  # pragma: no cover - surfaced via the future
            fut.set_exception(exc)
        return fut


def make_fake_runner(status, *, produce_body=True, reason="boom"):
    """A runner that mimics run_pipeline's status mapping without a subprocess."""

    def fake(job: Job, store: JobStore) -> None:
        store.set_status(job.id, RUNNING)
        if status in DOWNLOADABLE:
            specs = ARTIFACT_SPECS if produce_body else ARTIFACT_SPECS[:2]
            for suffix, _mime in specs:
                (job.workdir / f"{OUTPUT_BASE}{suffix}").write_bytes(b"glTF-fake-bytes")
            store.set_status(
                job.id,
                status,
                validated=(status == SUCCEEDED),
                artifacts=collect_artifacts(job.workdir),
            )
        else:
            store.set_status(job.id, status, reason=reason)

    return fake


def client_for(runner, tmp_path, **kwargs) -> TestClient:
    app = create_app(
        runner=runner,
        store=JobStore(),
        executor=SyncExecutor(),
        jobs_dir=tmp_path / "api_jobs",
        **kwargs,
    )
    return TestClient(app)


def _upload(client, *, filename="lm358.pdf", content=PDF_BYTES, content_type="application/pdf", part_number=None):
    data = {"part_number": part_number} if part_number else None
    return client.post("/jobs", files={"file": (filename, content, content_type)}, data=data)


def _upload_parse(client, *, filename="lm358.pdf", content=PDF_BYTES, content_type="application/pdf"):
    return client.post("/parse", files={"file": (filename, content, content_type)})


# --- health -------------------------------------------------------------------

def test_health(tmp_path):
    client = client_for(make_fake_runner(SUCCEEDED), tmp_path)
    assert client.get("/health").json() == {"status": "ok"}


# --- happy path ---------------------------------------------------------------

def test_upload_returns_202_with_job_id(tmp_path):
    client = client_for(make_fake_runner(SUCCEEDED), tmp_path)
    resp = _upload(client)
    assert resp.status_code == 202
    body = resp.json()
    assert body["job_id"]
    # With the inline executor the job has already run to completion.
    assert body["status"] in {"queued", SUCCEEDED}


def test_succeeded_job_lists_validated_artifacts(tmp_path):
    client = client_for(make_fake_runner(SUCCEEDED), tmp_path)
    job_id = _upload(client).json()["job_id"]

    status = client.get(f"/jobs/{job_id}").json()
    assert status["status"] == SUCCEEDED
    assert status["validated"] is True
    names = {a["name"] for a in status["artifacts"]}
    assert names == {
        f"{OUTPUT_BASE}_schematic.glb",
        f"{OUTPUT_BASE}_footprint.glb",
        f"{OUTPUT_BASE}_body.glb",
        f"{OUTPUT_BASE}_body.step",
    }


def test_artifact_download_returns_bytes_and_content_type(tmp_path):
    client = client_for(make_fake_runner(SUCCEEDED), tmp_path)
    job_id = _upload(client).json()["job_id"]
    status = client.get(f"/jobs/{job_id}").json()

    glb = next(a for a in status["artifacts"] if a["name"].endswith("_body.glb"))
    resp = client.get(glb["download_url"])
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "model/gltf-binary"
    assert resp.content == b"glTF-fake-bytes"

    step = next(a for a in status["artifacts"] if a["name"].endswith("_body.step"))
    assert client.get(step["download_url"]).headers["content-type"] == "application/step"


def test_body_skipped_still_succeeds(tmp_path):
    # Unsupported package family: CLI produces schematic+footprint only.
    client = client_for(make_fake_runner(SUCCEEDED, produce_body=False), tmp_path)
    job_id = _upload(client).json()["job_id"]
    names = {a["name"] for a in client.get(f"/jobs/{job_id}").json()["artifacts"]}
    assert names == {f"{OUTPUT_BASE}_schematic.glb", f"{OUTPUT_BASE}_footprint.glb"}


# --- unvalidated (best-effort) ------------------------------------------------

def test_unvalidated_job_still_serves_artifacts(tmp_path):
    client = client_for(make_fake_runner(UNVALIDATED), tmp_path)
    job_id = _upload(client).json()["job_id"]
    status = client.get(f"/jobs/{job_id}").json()
    assert status["status"] == UNVALIDATED
    assert status["validated"] is False
    glb = status["artifacts"][0]
    assert client.get(glb["download_url"]).status_code == 200


# --- failure states -----------------------------------------------------------

@pytest.mark.parametrize("status", ["failed", "error", "timeout"])
def test_failure_states_surface_reason_and_409_on_download(tmp_path, status):
    client = client_for(make_fake_runner(status, reason="unparseable input"), tmp_path)
    job_id = _upload(client).json()["job_id"]

    body = client.get(f"/jobs/{job_id}").json()
    assert body["status"] == status
    assert body["reason"] == "unparseable input"
    assert body["artifacts"] == []

    resp = client.get(f"/jobs/{job_id}/artifacts/{OUTPUT_BASE}_body.glb")
    assert resp.status_code == 409


# --- input & lookup errors ----------------------------------------------------

def test_non_pdf_upload_rejected_400(tmp_path):
    client = client_for(make_fake_runner(SUCCEEDED), tmp_path)
    resp = _upload(client, filename="notes.txt", content=b"hello", content_type="text/plain")
    assert resp.status_code == 400


def test_missing_file_rejected_400(tmp_path):
    client = client_for(make_fake_runner(SUCCEEDED), tmp_path)
    assert client.post("/jobs").status_code == 400


def test_unknown_job_404(tmp_path):
    client = client_for(make_fake_runner(SUCCEEDED), tmp_path)
    assert client.get("/jobs/does-not-exist").status_code == 404
    assert client.get("/jobs/does-not-exist/artifacts/x.glb").status_code == 404


def test_unknown_artifact_name_404(tmp_path):
    client = client_for(make_fake_runner(SUCCEEDED), tmp_path)
    job_id = _upload(client).json()["job_id"]
    assert client.get(f"/jobs/{job_id}/artifacts/nope.glb").status_code == 404


def test_path_traversal_artifact_name_rejected(tmp_path):
    client = client_for(make_fake_runner(SUCCEEDED), tmp_path)
    job_id = _upload(client).json()["job_id"]
    evil = quote("../../../../etc/passwd", safe="")
    resp = client.get(f"/jobs/{job_id}/artifacts/{evil}")
    # Not on the allowlist -> 404, never served from outside the work dir.
    assert resp.status_code == 404


# --- synchronous /parse endpoint (ZIP response) -------------------------------

def test_parse_sync_returns_zip_of_all_artifacts(tmp_path):
    import zipfile
    from io import BytesIO

    client = client_for(make_fake_runner(SUCCEEDED), tmp_path)
    resp = _upload_parse(client)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert resp.headers["x-job-status"] == SUCCEEDED
    assert resp.headers["x-validated"] == "true"
    assert "attachment" in resp.headers["content-disposition"]

    names = set(zipfile.ZipFile(BytesIO(resp.content)).namelist())
    assert names == {
        f"{OUTPUT_BASE}_schematic.glb",
        f"{OUTPUT_BASE}_footprint.glb",
        f"{OUTPUT_BASE}_body.glb",
        f"{OUTPUT_BASE}_body.step",
    }


def test_parse_sync_unvalidated_flags_header_but_still_zips(tmp_path):
    client = client_for(make_fake_runner(UNVALIDATED), tmp_path)
    resp = _upload_parse(client)
    assert resp.status_code == 200
    assert resp.headers["x-job-status"] == UNVALIDATED
    assert resp.headers["x-validated"] == "false"


@pytest.mark.parametrize("status,http", [("failed", 422), ("error", 500), ("timeout", 504)])
def test_parse_sync_failures_map_to_http_errors(tmp_path, status, http):
    client = client_for(make_fake_runner(status, reason="unparseable input"), tmp_path)
    resp = _upload_parse(client)
    assert resp.status_code == http
    assert resp.json()["detail"] == "unparseable input"


def test_parse_sync_non_pdf_rejected_400(tmp_path):
    client = client_for(make_fake_runner(SUCCEEDED), tmp_path)
    resp = client.post(
        "/parse", files={"file": ("notes.txt", b"hello", "text/plain")}
    )
    assert resp.status_code == 400


# --- queued -> running -> terminal transition (real threads) ------------------

def test_status_transitions_queued_running_succeeded(tmp_path):
    import threading

    release = threading.Event()
    started = threading.Event()

    def gated_runner(job, store):
        store.set_status(job.id, RUNNING)
        started.set()
        release.wait(timeout=5)
        store.set_status(job.id, SUCCEEDED, validated=True, artifacts=[])

    # Real executor so the runner blocks in a background thread.
    from concurrent.futures import ThreadPoolExecutor

    app = create_app(
        runner=gated_runner,
        store=JobStore(),
        executor=ThreadPoolExecutor(max_workers=1),
        jobs_dir=tmp_path / "api_jobs",
    )
    client = TestClient(app)

    job_id = _upload(client).json()["job_id"]
    assert started.wait(timeout=5)
    assert client.get(f"/jobs/{job_id}").json()["status"] == RUNNING
    release.set()
    # Poll until terminal.
    for _ in range(50):
        if client.get(f"/jobs/{job_id}").json()["status"] == SUCCEEDED:
            break
        import time

        time.sleep(0.05)
    assert client.get(f"/jobs/{job_id}").json()["status"] == SUCCEEDED


# --- opt-in real-CLI integration ---------------------------------------------

@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("API_INTEGRATION") != "1",
    reason="set API_INTEGRATION=1 to run the real-CLI integration test (hits the network)",
)
def test_real_cli_end_to_end(tmp_path):
    from src.api.jobs import run_pipeline

    fixture = Path("pdfs/lm358.pdf")
    assert fixture.is_file(), "expected pdfs/lm358.pdf fixture"

    client = client_for(run_pipeline, tmp_path)
    job_id = _upload(client, content=fixture.read_bytes()).json()["job_id"]

    body = client.get(f"/jobs/{job_id}").json()
    assert body["status"] in {SUCCEEDED, UNVALIDATED}
    assert body["artifacts"], "expected at least the schematic + footprint artifacts"
    first = body["artifacts"][0]
    assert client.get(first["download_url"]).status_code == 200


# --- work-dir cleanup + TTL sweep --------------------------------------------

def _job_dirs(jobs_dir: Path):
    return sorted(p.name for p in jobs_dir.iterdir() if p.is_dir()) if jobs_dir.exists() else []


def test_parse_deletes_workdir_after_response(tmp_path):
    # /parse's zip IS the response body; the work dir is scratch and must be gone
    # once the response is delivered (TestClient runs the BackgroundTask for us).
    jobs_dir = tmp_path / "api_jobs"
    client = client_for(make_fake_runner(SUCCEEDED), tmp_path)
    assert _upload_parse(client).status_code == 200
    assert _job_dirs(jobs_dir) == []


def test_parse_failure_deletes_workdir(tmp_path):
    # A failed sync parse hands nothing back, so its work dir must not linger.
    jobs_dir = tmp_path / "api_jobs"
    client = client_for(make_fake_runner(FAILED), tmp_path)
    assert _upload_parse(client).status_code == 422
    assert _job_dirs(jobs_dir) == []


def test_async_jobs_keep_workdir_for_download(tmp_path):
    # The async flow has a download-later step, so its files must persist.
    jobs_dir = tmp_path / "api_jobs"
    client = client_for(make_fake_runner(SUCCEEDED), tmp_path)
    job_id = _upload(client).json()["job_id"]
    assert job_id in _job_dirs(jobs_dir)
    first = client.get(f"/jobs/{job_id}").json()["artifacts"][0]
    assert client.get(first["download_url"]).status_code == 200


def test_sweep_removes_expired_dirs_and_evicts_records(tmp_path):
    jobs_dir = tmp_path / "api_jobs"
    jobs_dir.mkdir()
    store = JobStore()
    old = jobs_dir / "oldjob"
    old.mkdir()
    (old / f"{OUTPUT_BASE}_schematic.glb").write_bytes(b"x")
    store.add(Job(id="oldjob", workdir=old))
    os.utime(old, (0, 0))  # epoch mtime -> far past any TTL
    fresh = jobs_dir / "newjob"
    fresh.mkdir()
    store.add(Job(id="newjob", workdir=fresh))

    assert sweep_expired(store, jobs_dir, ttl_seconds=3600) == 1
    assert not old.exists() and fresh.exists()
    assert store.get("oldjob") is None and store.get("newjob") is not None


def test_sweep_reaps_restart_orphan_without_record(tmp_path):
    # After a restart the store is empty; aged on-disk dirs are still reaped.
    jobs_dir = tmp_path / "api_jobs"
    jobs_dir.mkdir()
    orphan = jobs_dir / "orphan"
    orphan.mkdir()
    (orphan / f"{OUTPUT_BASE}_body.step").write_bytes(b"x")
    os.utime(orphan, (0, 0))
    assert sweep_expired(JobStore(), jobs_dir, ttl_seconds=3600) == 1
    assert not orphan.exists()


def test_sweep_ttl_zero_disables(tmp_path):
    jobs_dir = tmp_path / "api_jobs"
    jobs_dir.mkdir()
    keep = jobs_dir / "keep"
    keep.mkdir()
    os.utime(keep, (0, 0))
    assert sweep_expired(JobStore(), jobs_dir, ttl_seconds=0) == 0
    assert keep.exists()
