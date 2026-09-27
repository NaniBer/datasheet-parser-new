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
from fastapi.responses import FileResponse, JSONResponse, Response
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
    run_extract,
    run_pipeline,
    sweep_expired,
)
from .models import Artifact, JobCreated, JobStatus
from ..agentic import repair_pins

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

    def _accept_upload(
        file: Optional[UploadFile],
        part_number: Optional[str],
        package: Optional[str] = None,
        pin_count: Optional[int] = None,
        model: Optional[str] = None,
    ) -> Job:
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

        job = Job(
            id=job_id, workdir=workdir, part_number=part_number or None,
            package=package or None, pin_count=pin_count, model=model or None,
        )
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
        package: Optional[str] = Form(None),
        pin_count: Optional[int] = Form(None),
        model: Optional[str] = Form(None),
    ) -> JobCreated:
        sweep_expired(store, jobs_dir)  # opportunistic TTL reap on each submit
        job = _accept_upload(file, part_number, package, pin_count, model)
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
        package: Optional[str] = Form(None),
        pin_count: Optional[int] = Form(None),
        model: Optional[str] = Form(None),
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
            job = _accept_upload(file, part_number, package, pin_count, model)
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

    @app.post(
        "/pins",
        responses={
            200: {"description": "Extracted pins as JSON"},
            422: {"description": "Datasheet could not be parsed"},
        },
    )
    def extract_pins(
        file: Optional[UploadFile] = File(None),
        part_number: Optional[str] = Form(None),
        package: Optional[str] = Form(None),
        pin_count: Optional[int] = Form(None),
        model: Optional[str] = Form(None),
    ) -> JSONResponse:
        """Extraction only: upload a PDF, get the pins back as JSON.

        Runs the pipeline through pin extraction and returns the pins directly —
        no GLB/geometry is built, so it's fast and cheap. Ideal for testing
        extraction or comparing models. Honors the same optional hints as
        ``/parse`` (``part_number`` / ``package`` / ``pin_count`` / ``model``).
        """
        sweep_expired(store, jobs_dir)  # opportunistic TTL reap on each submit
        if not parse_sem.acquire(blocking=False):
            raise HTTPException(
                status_code=503,
                detail="Server busy: too many concurrent runs. Retry shortly.",
            )
        try:
            job = _accept_upload(file, part_number, package, pin_count, model)
            status, data, reason = run_extract(job)
        finally:
            parse_sem.release()

        # The JSON is the whole response — nothing on disk is needed afterwards.
        cleanup_job(job, store)
        if data is None:
            raise HTTPException(
                status_code=_HTTP_FOR_STATUS.get(status, 500),
                detail=reason or f"Extraction ended with status {status!r}.",
            )
        return JSONResponse(content=data)

    @app.post(
        "/agentic",
        responses={
            200: {"description": "Extracted + repaired pins as JSON"},
            422: {"description": "Datasheet could not be parsed"},
        },
    )
    def extract_pins_agentic(
        file: Optional[UploadFile] = File(None),
        part_number: Optional[str] = Form(None),
        package: Optional[str] = Form(None),
        pin_count: Optional[int] = Form(None),
        model: Optional[str] = Form(None),
        repair_model: Optional[str] = Form(None),
        escalation_model: Optional[str] = Form(None),
    ) -> JSONResponse:
        """Extraction + agentic repair, one synchronous call, JSON back.

        Same as ``POST /pins`` (same hints, same extraction run, no GLB, no job
        id, no polling) followed by the repair layer in :mod:`src.agentic`:
        package-column check, deterministic range expansion, targeted text and
        vision repairs of grouped or garbled pin names, and an escalation to a
        stronger vision model only for groups the pinout drawing alone resolves.

        ``model`` is the extraction model (default LLM_MODEL). ``repair_model``
        (default: same as ``model``) does the cheap repairs. ``escalation_model``
        (default: AGENTIC_ESCALATION_MODEL, else anthropic/claude-opus-4.8) is
        used only when the cheap step cannot resolve a group.

        Response = the ``/pins`` body with repaired ``pins`` plus ``agentic``
        (``changed``, ``repairs`` log, ``flags``, ``usage`` of the repair calls)
        and ``usage_total`` (extraction + repair).
        """
        sweep_expired(store, jobs_dir)
        if not parse_sem.acquire(blocking=False):
            raise HTTPException(
                status_code=503,
                detail="Server busy: too many concurrent runs. Retry shortly.",
            )
        rep = None
        try:
            job = _accept_upload(file, part_number, package, pin_count, model)
            status, data, reason = run_extract(job)
            if data is not None:
                # Repair while the uploaded PDF is still on disk (the repair
                # reads page text and renders pages for the vision steps).
                try:
                    rep = repair_pins(
                        data.get("pins") or [],
                        job.input_pdf,
                        part_number or data.get("part_number"),
                        repair_model=repair_model or model or None,
                        escalation_model=escalation_model or None,
                        package=package or data.get("package") or None,
                        pin_count=pin_count or data.get("pin_count") or None,
                    )
                except Exception as exc:  # noqa: BLE001 - never lose the extraction
                    rep = {
                        "pins": data.get("pins") or [], "changed": 0,
                        "repairs": [f"repair layer failed: {type(exc).__name__}: {exc}"],
                        "flags": {"duplicates": [], "unresolved": [], "pin_count": len(data.get("pins") or [])},
                        "usage": {"repair_model": repair_model or model, "escalation_model": escalation_model,
                                  "calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
                                  "cost_usd": 0.0},
                    }
        finally:
            parse_sem.release()

        cleanup_job(job, store)
        if data is None:
            raise HTTPException(
                status_code=_HTTP_FOR_STATUS.get(status, 500),
                detail=reason or f"Extraction ended with status {status!r}.",
            )
        data["pins"] = rep["pins"]
        data["pin_count"] = len(rep["pins"])
        data["agentic"] = {k: rep[k] for k in ("changed", "repairs", "flags", "usage")}
        ex, ru = data.get("usage") or {}, rep["usage"]
        ex_cost, ru_cost = ex.get("cost_usd"), ru.get("cost_usd")
        data["usage_total"] = {
            "calls": (ex.get("calls") or 0) + (ru.get("calls") or 0),
            "prompt_tokens": (ex.get("prompt_tokens") or 0) + (ru.get("prompt_tokens") or 0),
            "completion_tokens": (ex.get("completion_tokens") or 0) + (ru.get("completion_tokens") or 0),
            "cost_usd": (None if ex_cost is None and ru_cost is None
                         else round((ex_cost or 0.0) + (ru_cost or 0.0), 6)),
        }
        return JSONResponse(content=data)

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
