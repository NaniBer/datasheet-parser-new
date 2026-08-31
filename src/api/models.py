"""Pydantic response schemas for the HTTP API."""

from typing import List, Optional

from pydantic import BaseModel


class Artifact(BaseModel):
    """A single downloadable output file produced by a job."""

    name: str
    type: str  # MIME type, e.g. "model/gltf-binary" or "application/step"
    size: int  # bytes
    download_url: str


class JobCreated(BaseModel):
    """Response for a freshly accepted job (202)."""

    job_id: str
    status: str


class JobStatus(BaseModel):
    """Full status of a job returned by GET /jobs/{id}."""

    job_id: str
    status: str
    # None until the job reaches a terminal state; then True for a fully
    # validated run, False for a best-effort (unvalidated) one.
    validated: Optional[bool] = None
    artifacts: List[Artifact] = []
    # Actionable message (tail of CLI output) for the non-success states.
    reason: Optional[str] = None
