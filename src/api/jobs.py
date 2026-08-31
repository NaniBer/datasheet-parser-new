"""
Job model, in-memory store, and the subprocess pipeline runner.

The runner spawns the existing CLI (``python -m src.main``) as a subprocess so
that a cadquery/OCCT or LLM-client crash cannot take down the API server, and
so the CLI's documented exit-code contract maps directly onto job status.
This mirrors the pattern already used by ``tools/run_full_flow_eval.py``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# --- Job status values --------------------------------------------------------
QUEUED = "queued"
RUNNING = "running"
SUCCEEDED = "succeeded"
UNVALIDATED = "unvalidated"
FAILED = "failed"
ERROR = "error"
TIMEOUT = "timeout"

# Terminal states whose artifacts are downloadable.
DOWNLOADABLE = {SUCCEEDED, UNVALIDATED}

# --- CLI exit-code contract (see src/main.py header) --------------------------
EXIT_OK = 0          # all artifacts produced & validated
EXIT_DOMAIN = 1      # domain failure (unparseable / fail-closed)
EXIT_INTERNAL = 2    # internal error (bug)
EXIT_DEGRADED = 3    # produced but UNVALIDATED (best-effort)

_STATUS_FOR_EXIT = {
    EXIT_OK: SUCCEEDED,
    EXIT_DEGRADED: UNVALIDATED,
    EXIT_DOMAIN: FAILED,
    EXIT_INTERNAL: ERROR,
}

# Base stem used for the CLI output argument inside each job's work dir. The
# CLI derives the artifact filenames below from it.
OUTPUT_BASE = "output"

# (suffix appended by the CLI, MIME type). Order = display order.
ARTIFACT_SPECS = [
    ("_schematic.glb", "model/gltf-binary"),
    ("_footprint.glb", "model/gltf-binary"),
    ("_body.glb", "model/gltf-binary"),
    ("_body.step", "application/step"),
]

# Tunables (reuse the flow-eval defaults so behaviour matches the CLI runner).
JOB_TIMEOUT = int(os.environ.get("API_JOB_TIMEOUT", os.environ.get("FLOW_EVAL_TIMEOUT", "360")))
WORKERS = int(os.environ.get("API_WORKERS", os.environ.get("FLOW_EVAL_WORKERS", "4")))

# How much CLI output to keep as the failure `reason`.
_REASON_TAIL = 2000


@dataclass
class ArtifactRecord:
    """A produced output file, before it is turned into a response model."""

    name: str
    path: Path
    type: str
    size: int


@dataclass
class Job:
    """A single parse request and its evolving state."""

    id: str
    workdir: Path
    part_number: Optional[str] = None
    status: str = QUEUED
    validated: Optional[bool] = None
    reason: Optional[str] = None
    artifacts: List[ArtifactRecord] = field(default_factory=list)

    @property
    def input_pdf(self) -> Path:
        return self.workdir / "input.pdf"


class JobStore:
    """Thread-safe in-memory registry of jobs.

    YAGNI on Redis/Celery for v1: jobs and their status are lost on server
    restart. The artifact files on disk survive (never auto-deleted).
    """

    def __init__(self) -> None:
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()

    def add(self, job: Job) -> None:
        with self._lock:
            self._jobs[job.id] = job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def set_status(
        self,
        job_id: str,
        status: str,
        *,
        validated: Optional[bool] = None,
        reason: Optional[str] = None,
        artifacts: Optional[List[ArtifactRecord]] = None,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = status
            if validated is not None:
                job.validated = validated
            if reason is not None:
                job.reason = reason
            if artifacts is not None:
                job.artifacts = artifacts


def collect_artifacts(workdir: Path, base: str = OUTPUT_BASE) -> List[ArtifactRecord]:
    """Scan a work dir for the artifacts the CLI is expected to have produced.

    Only files that actually exist are returned — the 3D body is best-effort
    and unsupported package families are skipped without failing the run.
    """
    records: List[ArtifactRecord] = []
    for suffix, mime in ARTIFACT_SPECS:
        path = workdir / f"{base}{suffix}"
        if path.is_file():
            records.append(
                ArtifactRecord(name=path.name, path=path, type=mime, size=path.stat().st_size)
            )
    return records


def run_pipeline(job: Job, store: JobStore) -> None:
    """Real runner: run the CLI subprocess and map its result onto job status.

    Injected into the app; tests substitute a fake with the same signature.
    """
    store.set_status(job.id, RUNNING)

    output = job.workdir / f"{OUTPUT_BASE}.glb"
    cmd = [
        sys.executable, "-m", "src.main",
        str(job.input_pdf), str(output),
        "--both", "--body-3d",
    ]
    if job.part_number:
        cmd += ["--part-number", job.part_number]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=JOB_TIMEOUT,
            cwd=Path(__file__).resolve().parents[2],  # repo root, so `-m src.main` resolves
        )
    except subprocess.TimeoutExpired as exc:
        tail = (exc.stderr or exc.stdout or "")
        if isinstance(tail, bytes):
            tail = tail.decode(errors="replace")
        store.set_status(
            job.id,
            TIMEOUT,
            reason=f"Job exceeded API_JOB_TIMEOUT ({JOB_TIMEOUT}s).\n{tail[-_REASON_TAIL:]}".strip(),
        )
        return

    status = _STATUS_FOR_EXIT.get(proc.returncode, ERROR)

    if status in DOWNLOADABLE:
        store.set_status(
            job.id,
            status,
            validated=(status == SUCCEEDED),
            artifacts=collect_artifacts(job.workdir),
        )
    else:
        tail = (proc.stderr or proc.stdout or "").strip()
        store.set_status(job.id, status, reason=tail[-_REASON_TAIL:] or None)
