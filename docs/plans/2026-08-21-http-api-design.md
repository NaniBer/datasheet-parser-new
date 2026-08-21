# HTTP API for the Datasheet Parser — Design

**Date:** 2026-08-21
**Status:** Approved (design), pending implementation plan
**Scope:** Add an HTTP API that wraps the existing CLI pipeline so callers can
upload a PDF datasheet and retrieve the generated GLB/STEP artifacts. This is a
**thin async wrapper over the proven CLI**, not a reimplementation of the
pipeline.

---

## 1. Decisions (locked)

| Decision | Choice | Rationale |
|---|---|---|
| Processing model | **Async job + poll** | A full parse runs the LLM pipeline + cadquery build, ~1–2 min/PDF. Blocking HTTP would risk timeouts and tie up a worker for minutes. |
| Input | **PDF file upload (multipart)** | Self-contained; works for any caller. Optional `part_number` field for variant steering. |
| Output | **GLB/STEP artifact downloads** | Return download URLs + minimal metadata. No structured pin-data JSON in v1 (not requested). |
| Artifacts generated | **Full set, always** | schematic + footprint(=2D PCB) + 3D body. No per-request artifact selection in v1. |
| Framework | **FastAPI + Uvicorn** | Native multipart, background execution, auto OpenAPI docs. |

Out of scope for v1 (easy to add later): auth, persistent DB/queue, rate
limiting, structured pin-data JSON response, per-request artifact selection.

---

## 2. Architecture

The API is a thin layer. Each job spawns the **existing CLI** as a subprocess:

```
python -m src.main <uploaded.pdf> <workdir>/<stem>.glb --both --body-3d [--part-number X]
```

This reuses the exact validated pipeline with two benefits:
- **Process isolation** — a cadquery/OCCT or LLM-client crash cannot take down
  the API server.
- **Exit-code contract reuse** — the CLI's documented exit codes map directly
  to job status (see §4). Same pattern already used by
  `tools/run_full_flow_eval.py`.

```
POST /jobs (multipart: file, part_number?)
    -> save api_jobs/<uuid>/input.pdf ; status=queued ; submit to ThreadPoolExecutor
    -> 202 { job_id, status }

[worker thread] status=running
    -> subprocess: python -m src.main input.pdf <workdir>/<stem>.glb --both --body-3d
    -> map exit code -> status ; collect produced files

GET /jobs/{id}
    -> { status, validated, artifacts: [{name, type, size, download_url}], reason? }

GET /jobs/{id}/artifacts/{name}
    -> streams the GLB/STEP (FileResponse)

GET /health
    -> { status: "ok" }
```

### Artifacts produced per job
From one `--both --body-3d` invocation:
- `<stem>_schematic.glb` — schematic / pinout symbol
- `<stem>_footprint.glb` — 2D PCB footprint
- `<stem>_body.glb` — 3D package body (web)
- `<stem>_body.step` — 3D package body (B-rep CAD)

The 3D body is best-effort: unsupported package families are skipped by the CLI
without failing the run (the job still succeeds with the other artifacts).

---

## 3. Components (`src/api/`)

Mirrors existing package conventions (`src/schematic_generator/`, `src/model3d/`).

- `app.py` — FastAPI app + route handlers. Wires the job store and runner.
- `jobs.py` — `JobStore` (in-memory dict + `threading.Lock`), `Job` dataclass,
  and the subprocess **runner** (`run_pipeline(job, ...)`). The runner is
  injected into the app so tests can substitute a fake.
- `models.py` — pydantic response schemas (`JobCreated`, `JobStatus`,
  `Artifact`).

### Job store
- In-memory `dict[job_id, Job]` guarded by a lock. **YAGNI on Redis/Celery for
  v1.** Documented tradeoff: jobs and their in-memory status are lost on server
  restart (the artifact files on disk survive).
- One work dir per job: `api_jobs/<job_id>/` containing `input.pdf` and outputs.
- Artifacts are **never auto-deleted** (project rule: move, don't delete output
  folders). A TTL/cleanup job is deferred.

### Concurrency
- A module-level `ThreadPoolExecutor` (worker count from `API_WORKERS`, default
  matching `FLOW_EVAL_WORKERS`) runs jobs. Subprocess model means the GIL is not
  a bottleneck.
- Per-job subprocess timeout (`API_JOB_TIMEOUT`, default ~360s, reusing the
  `FLOW_EVAL_TIMEOUT` value) — a hung LLM call fails one job, not the server.

---

## 4. Data flow & status mapping

| CLI exit | Meaning | Job status | Artifacts downloadable? |
|---|---|---|---|
| 0 | all artifacts produced & validated | `succeeded` | yes (`validated=true`) |
| 3 | produced but UNVALIDATED (best-effort) | `unvalidated` | yes (`validated=false`) |
| 1 | domain failure (unparseable / fail-closed) | `failed` | no |
| 2 | internal error (bug) | `error` | no |
| (timeout) | subprocess exceeded `API_JOB_TIMEOUT` | `timeout` | no |

`GET /jobs/{id}` returns `reason` (tail of CLI stderr/stdout) for the
non-success states so callers get an actionable message.

---

## 5. Error handling (HTTP)

- Non-PDF upload (bad content-type or missing file) → **400**.
- Unknown `job_id` → **404**.
- Artifact requested before job completes, or on a failed job → **409** with the
  current status.
- Unknown artifact name on a completed job → **404**.
- Path traversal on artifact name → reject (serve only files inside the job's
  work dir, match against the known artifact list).

---

## 6. Testing

- **FastAPI `TestClient`**, runner **dependency-injected** so the suite never
  calls the real LLM/vision backends or cadquery. The fake runner writes small
  placeholder `.glb`/`.step` files and sets a chosen exit status.
- Cases: upload → `202 {job_id}`; poll transitions queued→running→succeeded;
  artifact download returns bytes with correct content-type; `unvalidated`
  job still serves artifacts; `failed`/`error`/`timeout` surface `reason` and
  409 on download; 400 on non-PDF; 404 on unknown job/artifact.
- One **opt-in** integration test (marker/env-gated) that runs the real CLI on a
  small fixture PDF (e.g. `pdfs/lm358.pdf`) — excluded from the default suite
  because it hits the network and is non-deterministic.

---

## 7. Dependencies & running

Add to `requirements.txt` / `pyproject.toml`: `fastapi`, `uvicorn[standard]`,
`python-multipart`.

Run locally:
```bash
uvicorn src.api.app:app --reload
# docs at http://127.0.0.1:8000/docs
```

---

## 8. File plan

New:
- `src/api/__init__.py`
- `src/api/app.py`
- `src/api/jobs.py`
- `src/api/models.py`
- `tests/test_api.py`

Modified:
- `requirements.txt`, `pyproject.toml` — add deps.
- `README.md` — API usage section.
