"""
FastAPI application: routes, job store wiring, and the pipeline runner.

Run locally:
    uvicorn src.api.app:app --reload
    # interactive docs at http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import io
import os
import shutil
import threading
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from starlette.background import BackgroundTask

from .jobs import (
    DOWNLOADABLE,
    ERROR,
    FAILED,
    TIMEOUT,
    WORKERS,
    Job,
    JobStore,
    cleanup_job,
    run_pipeline,
    sweep_expired,
)
from .models import Artifact, JobCreated, JobStatus

# Non-downloadable terminal states -> HTTP status for the synchronous endpoint.
_HTTP_FOR_STATUS = {
    FAILED: 422,   # domain failure: the datasheet was unparseable
    ERROR: 500,    # internal error (a bug)
    TIMEOUT: 504,  # pipeline exceeded API_JOB_TIMEOUT
}

# Injectable runner signature: (job, store) -> None, executed in a worker thread.
Runner = Callable[[Job, JobStore], None]

DEFAULT_JOBS_DIR = Path(os.environ.get("API_JOBS_DIR", "api_jobs"))

# Safety guards (tunable via env). Even internal, these stop one large PDF from
# OOMing a worker and stop many concurrent /parse calls from spawning unbounded
# OCCT subprocesses.
MAX_UPLOAD_BYTES = int(os.environ.get("API_MAX_UPLOAD_MB", "25")) * 1024 * 1024
MAX_CONCURRENT_PARSE = int(os.environ.get("API_MAX_CONCURRENT_PARSE", "2"))
_UPLOAD_CHUNK = 1 << 20  # 1 MiB


def create_app(
    runner: Runner = run_pipeline,
    store: Optional[JobStore] = None,
    executor: Optional[ThreadPoolExecutor] = None,
    jobs_dir: Optional[Path] = None,
) -> FastAPI:
    """Build the app. `runner` is injected so tests can swap in a fake."""
    store = store or JobStore()
    executor = executor or ThreadPoolExecutor(max_workers=WORKERS)
    jobs_dir = jobs_dir or DEFAULT_JOBS_DIR
    jobs_dir.mkdir(parents=True, exist_ok=True)
    # On boot the in-memory store is empty, so any work dirs left on disk are
    # restart-orphans; reap the ones past the TTL now, then opportunistically on
    # each new submit (no background thread needed).
    sweep_expired(store, jobs_dir)
    # Bounds the number of in-flight synchronous /parse builds (each spawns an
    # OCCT subprocess); excess callers get a 503 rather than exhausting the host.
    parse_sem = threading.Semaphore(MAX_CONCURRENT_PARSE)

    app = FastAPI(
        title="Datasheet Parser API",
        description="Upload a PDF datasheet; retrieve generated GLB/STEP artifacts.",
        version="0.1.0",
    )

    def _to_status(job: Job) -> JobStatus:
        artifacts = [
            Artifact(
                name=a.name,
                type=a.type,
                size=a.size,
                download_url=f"/jobs/{job.id}/artifacts/{a.name}",
            )
            for a in job.artifacts
        ]
        return JobStatus(
            job_id=job.id,
            status=job.status,
            validated=job.validated,
            artifacts=artifacts,
            reason=job.reason,
        )

    def _accept_upload(file: Optional[UploadFile], part_number: Optional[str]) -> Job:
        """Validate the upload, persist it to a fresh work dir, register the job."""
        if file is None or not file.filename:
            raise HTTPException(status_code=400, detail="A PDF file upload is required.")
        is_pdf = (file.content_type == "application/pdf") or file.filename.lower().endswith(".pdf")
        if not is_pdf:
            raise HTTPException(
                status_code=400,
                detail=f"Expected a PDF upload, got content-type {file.content_type!r}.",
            )

        job_id = uuid.uuid4().hex
        workdir = jobs_dir / job_id
        workdir.mkdir(parents=True, exist_ok=True)

        job = Job(id=job_id, workdir=workdir, part_number=part_number or None)
        # Stream to disk with a hard size cap so a huge/bomb upload can't OOM us.
        size = 0
        try:
            with job.input_pdf.open("wb") as out:
                while True:
                    chunk = file.file.read(_UPLOAD_CHUNK)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise HTTPException(
                            status_code=413,
                            detail=f"PDF exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.",
                        )
                    out.write(chunk)
        except Exception:
            shutil.rmtree(workdir, ignore_errors=True)  # don't leave a partial dir
            raise

        store.add(job)
        return job

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/jobs", response_model=JobCreated, status_code=202)
    def create_job(
        file: Optional[UploadFile] = File(None),
        part_number: Optional[str] = Form(None),
    ) -> JobCreated:
        sweep_expired(store, jobs_dir)  # opportunistic TTL reap on each submit
        job = _accept_upload(file, part_number)
        executor.submit(runner, job, store)
        return JobCreated(job_id=job.id, status=job.status)

    @app.post(
        "/parse",
        responses={
            200: {"content": {"application/zip": {}}, "description": "ZIP of all artifacts"},
            422: {"description": "Datasheet could not be parsed"},
        },
    )
    def parse_sync(
        file: Optional[UploadFile] = File(None),
        part_number: Optional[str] = Form(None),
    ) -> Response:
        """Blocking parse: upload a PDF, get all artifacts back as one ZIP.

        Runs the full pipeline inline (~1-2 min) — no polling. The connection is
        held for the whole run, so callers/proxies must allow a long timeout.
        """
        sweep_expired(store, jobs_dir)  # opportunistic TTL reap on each submit
        if not parse_sem.acquire(blocking=False):
            raise HTTPException(
                status_code=503,
                detail="Server busy: too many concurrent parses. Retry shortly, "
                       "or use the async POST /jobs endpoint.",
            )
        try:
            job = _accept_upload(file, part_number)
            runner(job, store)  # blocks until the pipeline finishes
        finally:
            parse_sem.release()

        if job.status not in DOWNLOADABLE:
            # Nothing to hand back — drop the work dir before surfacing the error.
            cleanup_job(job, store)
            raise HTTPException(
                status_code=_HTTP_FOR_STATUS.get(job.status, 500),
                detail=job.reason or f"Parse ended with status {job.status!r}.",
            )

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for art in job.artifacts:
                zf.write(art.path, arcname=art.name)
        zip_bytes = buf.getvalue()  # the zip now lives fully in memory

        # The zip IS the response body (never written to disk) and /parse has no
        # download-later step, so the work dir is pure scratch. Delete it — and the
        # now-useless record — AFTER the response is fully sent, via a BackgroundTask.
        stem = Path(file.filename).stem if file and file.filename else "artifacts"
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            background=BackgroundTask(cleanup_job, job, store),
            headers={
                "Content-Disposition": f'attachment; filename="{stem}_artifacts.zip"',
                "X-Job-Status": job.status,
                "X-Validated": "true" if job.validated else "false",
            },
        )

    @app.get("/jobs/{job_id}", response_model=JobStatus)
    def get_job(job_id: str) -> JobStatus:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Unknown job {job_id!r}.")
        return _to_status(job)

    @app.get("/jobs/{job_id}/artifacts/{name}")
    def download_artifact(job_id: str, name: str) -> FileResponse:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Unknown job {job_id!r}.")
        if job.status not in DOWNLOADABLE:
            raise HTTPException(
                status_code=409,
                detail=f"Job {job_id!r} is {job.status!r}; no artifacts available.",
            )
        # The stored artifact list is the allowlist: matching by name means a
        # traversal path like "../../etc/passwd" simply won't be found (404).
        match = next((a for a in job.artifacts if a.name == name), None)
        if match is None:
            raise HTTPException(status_code=404, detail=f"Unknown artifact {name!r}.")
        return FileResponse(path=match.path, media_type=match.type, filename=match.name)

    return app


app = create_app()
