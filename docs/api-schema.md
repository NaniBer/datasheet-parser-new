# Datasheet Parser API — Input / Output Schema

HTTP API (`src/api/`, FastAPI) that takes a **PDF datasheet** and returns the
generated **3D artifacts** (schematic symbol, PCB footprint, 3D body) as GLB +
STEP files.

- **Production base URL:** `https://datasheet-parser.ideeza.com`
- **Base URL (local):** `http://127.0.0.1:8000`
- **Interactive docs (Swagger):** `/docs` — **VPN-only** in production (`https://datasheet-parser.ideeza.com/docs`); open locally at `http://127.0.0.1:8000/docs`. Raw schema at `/openapi.json`.
- **Version:** `0.1.0`
- **Auth:** send header **`apikey: <KEY>`** on **every** request except `GET /health` (the only open route). Missing/invalid key is rejected at the gateway. **Never commit the key** — pass it via an env var / secret.

### Auth + the `part_number` requirement (read first)

```bash
export DP_KEY='…your key…'          # do NOT hard-code / commit this
export DP_URL='https://datasheet-parser.ideeza.com'
```

- **Always send `part_number`.** Without it the footprint step fails on a missing
  reference file `/app/2d.glb` and the API returns **`422`**.
- **Note — deployed-image caveat (verified 2026-09-02).** On the currently
  deployed image, `part_number` alone does **not** rescue every part: several
  still hit the same `/app/2d.glb` reference failure (`422`). Verified live:
  | Part (`part_number`) | Result |
  |----------------------|--------|
  | `AMS1117` | **`200`** — all 4 artifacts ✅ |
  | `NE555` | `422` — `Reference GLB not found: /app/2d.glb` |
  | `LM358` | `422` — same |
  So the pipeline + auth work end-to-end (proven with AMS1117), but that
  reference-GLB check still blocks some packages until the deploy bundles
  `/app/2d.glb` (or the check is made fail-open).
- Production limits: **25 MB** upload, **2** concurrent parses (`503` if busy),
  **360 s** per job. `POST /parse` is ~25 s for a small part.

---

## Endpoints at a glance

| Method | Path | Purpose | Success |
|--------|------|---------|---------|
| `GET`  | `/health` | Liveness probe | `200` `{"status":"ok"}` |
| `POST` | `/jobs` | **Async** submit — returns a `job_id` immediately | `202` `JobCreated` |
| `GET`  | `/jobs/{job_id}` | Poll job status + artifact list | `200` `JobStatus` |
| `GET`  | `/jobs/{job_id}/artifacts/{name}` | Download one artifact file | `200` binary |
| `POST` | `/parse` | **Sync** — blocks, returns a ZIP of all artifacts | `200` `application/zip` |

Two modes:
- **Async (`/jobs` → poll `/jobs/{id}` → download `/artifacts/{name}`)** — recommended; a parse takes ~1–2 min.
- **Sync (`/parse`)** — one call, connection held open for the whole run, ZIP streamed back. Callers/proxies must allow a long read timeout.

**Error body shape.** Every non-2xx response (except raw binary downloads) is JSON. Application errors use FastAPI's standard shape:
```json
{ "detail": "Expected a PDF upload, got content-type 'text/plain'." }
```
Request-validation errors (malformed multipart, wrong field types) return a list:
```json
{ "detail": [ { "loc": ["body", "file"], "msg": "field required", "type": "value_error.missing" } ] }
```

---

## Per-endpoint reference (schema · errors · example in → out)

### 1. `GET /health`
Liveness probe. No input.

- **Request:** `GET /health` — no params, no body.
- **Output schema:** `{ "status": "ok" }`
- **Error codes:** none (always `200` if the process is up).

**Example** (the only route that needs **no** `apikey`)
```bash
curl "$DP_URL/health"
```
```json
{ "status": "ok" }
```

---

### 2. `POST /jobs` — async submit
Accepts the upload, registers a job, returns immediately with a `job_id`.

- **Request schema** (`multipart/form-data`):
  | Field | Type | Required | Notes |
  |-------|------|----------|-------|
  | `file` | binary (PDF) | **yes** | PDF datasheet; validated by content-type or `.pdf` suffix |
  | `part_number` | string | no | Disambiguates a multi-part datasheet |
- **Output schema** — `202` `JobCreated`: `{ "job_id": string, "status": string }`
- **Probable error codes:**
  | Code | Cause | Example body |
  |------|-------|--------------|
  | `400` | No file, or non-PDF | `{ "detail": "A PDF file upload is required." }` |
  | `413` | Upload > 25 MB | `{ "detail": "PDF exceeds the 25 MB limit." }` |
  | `422` | Malformed multipart / missing field | `{ "detail": [ { "loc": ["body","file"], "msg": "field required", ... } ] }` |

**Example input**
```bash
curl -s -X POST "$DP_URL/jobs" \
  -H "apikey: $DP_KEY" \
  -F "file=@pdfs/74HC595_TI.pdf" \
  -F "part_number=SN74HC595"           # ALWAYS send part_number
```
**Corresponding output** (`202`)
```json
{ "job_id": "60333c6d0a9b4d0a857b50276c543fd0", "status": "queued" }
```

---

### 3. `GET /jobs/{job_id}` — poll status
Returns the job's current state and, once terminal & downloadable, its artifact list.

- **Request schema:** path param `job_id` (hex string from step 2). No body.
- **Output schema** — `200` `JobStatus` (see the full field tables below).
- **Probable error codes:**
  | Code | Cause | Example body |
  |------|-------|--------------|
  | `404` | Unknown `job_id` | `{ "detail": "Unknown job 'abc123'." }` |

**Example input**
```bash
curl -s -H "apikey: $DP_KEY" \
  "$DP_URL/jobs/60333c6d0a9b4d0a857b50276c543fd0"
```
**Corresponding output while running** (`200`)
```json
{ "job_id": "60333c6d0a9b4d0a857b50276c543fd0", "status": "running",
  "validated": null, "artifacts": [], "reason": null }
```
**Corresponding output once finished** (`200`) — real response:
```json
{
  "job_id": "60333c6d0a9b4d0a857b50276c543fd0",
  "status": "succeeded",
  "validated": true,
  "artifacts": [
    { "name": "output_schematic.glb", "type": "model/gltf-binary", "size": 2823960,
      "download_url": "/jobs/60333c6d0a9b4d0a857b50276c543fd0/artifacts/output_schematic.glb" },
    { "name": "output_footprint.glb", "type": "model/gltf-binary", "size": 1215072,
      "download_url": "/jobs/60333c6d0a9b4d0a857b50276c543fd0/artifacts/output_footprint.glb" },
    { "name": "output_body.glb", "type": "model/gltf-binary", "size": 534552,
      "download_url": "/jobs/60333c6d0a9b4d0a857b50276c543fd0/artifacts/output_body.glb" },
    { "name": "output_body.step", "type": "application/step", "size": 847560,
      "download_url": "/jobs/60333c6d0a9b4d0a857b50276c543fd0/artifacts/output_body.step" }
  ],
  "reason": null
}
```
**Corresponding output on a domain failure** (`200`, but `status: failed`):
```json
{ "job_id": "…", "status": "failed", "validated": false, "artifacts": [],
  "reason": "Datasheet unparseable: no pin table found.\n…(tail of CLI output)…" }
```

---

### 4. `GET /jobs/{job_id}/artifacts/{name}` — download one file
Streams a single generated artifact.

- **Request schema:** path params `job_id` and `name` (the exact `name` from the `artifacts` list — acts as an allowlist).
- **Output:** raw bytes, `Content-Type` = the artifact MIME, `Content-Disposition: attachment; filename="<name>"`.
- **Probable error codes:**
  | Code | Cause | Example body |
  |------|-------|--------------|
  | `404` | Unknown job or artifact name | `{ "detail": "Unknown artifact 'foo.glb'." }` |
  | `409` | Job not in a downloadable state (still running/failed) | `{ "detail": "Job '…' is 'running'; no artifacts available." }` |

**Example input**
```bash
curl -s -OJ -H "apikey: $DP_KEY" \
  "$DP_URL/jobs/60333c6d0a9b4d0a857b50276c543fd0/artifacts/output_schematic.glb"
```
**Corresponding output**: binary GLB written to `output_schematic.glb` (2,823,960 bytes), `Content-Type: model/gltf-binary`.

---

### 5. `POST /parse` — synchronous parse
Blocks for the whole pipeline (~1–2 min) and streams back **all** artifacts as one ZIP.

- **Request schema:** identical to `POST /jobs` (`file` + optional `part_number`).
- **Output:** `200` `application/zip` (all artifacts), with headers `Content-Disposition: attachment; filename="<pdf-stem>_artifacts.zip"`, `X-Job-Status`, `X-Validated`.
- **Probable error codes:**
  | Code | Cause | Example body |
  |------|-------|--------------|
  | `400` | No file / non-PDF | `{ "detail": "A PDF file upload is required." }` |
  | `413` | Upload > 25 MB | `{ "detail": "PDF exceeds the 25 MB limit." }` |
  | `422` | Datasheet could not be parsed (domain failure) | `{ "detail": "Datasheet unparseable: …" }` |
  | `500` | Internal error (bug) | `{ "detail": "Parse ended with status 'error'." }` |
  | `503` | Too many concurrent parses | `{ "detail": "Server busy: too many concurrent parses. …" }` |
  | `504` | Pipeline exceeded the timeout | `{ "detail": "Job exceeded API_JOB_TIMEOUT (360s). …" }` |

**Example input** (a part verified live — see the deployed-image caveat above)
```bash
curl -s -X POST "$DP_URL/parse" \
  -H "apikey: $DP_KEY" \
  -F "file=@pdfs/AMS1117.pdf" \
  -F "part_number=AMS1117" \
  -OJ -D headers.txt                   # ZIP + response headers
```
**Corresponding output** (real, captured 2026-09-02): binary ZIP written to `AMS1117_artifacts.zip` (698 KB) containing the four artifacts — validated as well-formed GLB/STEP:
```
output_schematic.glb   1609112 bytes   model/gltf-binary
output_footprint.glb    616412 bytes   model/gltf-binary
output_body.glb         377292 bytes   model/gltf-binary
output_body.step        546413 bytes   application/step
```
Response headers:
```
HTTP/2 200
content-type: application/zip
content-disposition: attachment; filename="AMS1117_artifacts.zip"
x-job-status: succeeded
x-validated: true
```

---

## Input schema (request)

Both `POST /jobs` and `POST /parse` take the **same** `multipart/form-data` body:

| Field | In | Type | Required | Notes |
|-------|----|------|----------|-------|
| `file` | form-data | binary (PDF) | **yes** | The datasheet. Must be a PDF (checked by `content-type: application/pdf` **or** a `.pdf` filename). |
| `part_number` | form-data | string | no | Optional hint to disambiguate which part in a multi-part datasheet. |

**Limits / guards** (env-tunable):
- Max upload: **25 MB** (`API_MAX_UPLOAD_MB`) → over-size returns **`413`**.
- Max concurrent sync parses: **2** (`API_MAX_CONCURRENT_PARSE`) → excess `/parse` callers get **`503`**.
- Per-job timeout: **360 s** (`API_JOB_TIMEOUT`) → **`504` / `timeout`** status.

**Example — async submit:**
```bash
curl -s -X POST "$DP_URL/jobs" -H "apikey: $DP_KEY" \
  -F "file=@pdfs/74HC595_TI.pdf" \
  -F "part_number=SN74HC595D"
```

**Example — sync parse (ZIP back):**
```bash
curl -s -X POST "$DP_URL/parse" -H "apikey: $DP_KEY" \
  -F "file=@pdfs/74HC595_TI.pdf" -F "part_number=SN74HC595D" -OJ
```

---

## Output schema (responses)

### `POST /jobs` → `202` — `JobCreated`
```json
{
  "job_id": "b1c2d3e4f5a6...",   // hex uuid, use for polling/downloads
  "status": "queued"
}
```

### `GET /jobs/{job_id}` → `200` — `JobStatus`
```json
{
  "job_id": "b1c2d3e4f5a6...",
  "status": "succeeded",
  "validated": true,
  "artifacts": [
    {
      "name": "output_schematic.glb",
      "type": "model/gltf-binary",
      "size": 812345,
      "download_url": "/jobs/b1c2d3e4f5a6.../artifacts/output_schematic.glb"
    },
    { "name": "output_footprint.glb", "type": "model/gltf-binary", "size": 1247628, "download_url": "..." },
    { "name": "output_body.glb",      "type": "model/gltf-binary", "size": 689200,  "download_url": "..." },
    { "name": "output_body.step",     "type": "application/step",  "size": 45120,   "download_url": "..." }
  ],
  "reason": null
}
```

**`JobStatus` fields:**

| Field | Type | Meaning |
|-------|------|---------|
| `job_id` | string | The job id. |
| `status` | string | Lifecycle state — see table below. |
| `validated` | bool \| null | `null` until terminal. Then `true` = fully conformance-validated run, `false` = best-effort (produced but unvalidated). |
| `artifacts` | `Artifact[]` | Empty until the job produces files. See `Artifact` below. |
| `reason` | string \| null | Actionable message (tail of pipeline output, ≤2000 chars) for non-success terminal states; `null` on success. |

**`Artifact` object:**

| Field | Type | Meaning |
|-------|------|---------|
| `name` | string | Filename; also the `{name}` path segment for download (acts as an allowlist — traversal names 404). |
| `type` | string | MIME type: `model/gltf-binary` (GLB) or `application/step` (STEP). |
| `size` | int | Size in bytes. |
| `download_url` | string | Relative URL: `/jobs/{job_id}/artifacts/{name}`. |

### `GET /jobs/{job_id}/artifacts/{name}` → `200`
Raw file bytes with the artifact's MIME type and a `filename` content-disposition. `409` if the job isn't in a downloadable state; `404` for unknown job/artifact.

### `POST /parse` → `200` — `application/zip`
Binary ZIP of all artifacts. Extra headers:
- `Content-Disposition: attachment; filename="<pdf-stem>_artifacts.zip"`
- `X-Job-Status: succeeded | unvalidated`
- `X-Validated: true | false`

---

## Job lifecycle (`status` values)

| `status` | Terminal? | Downloadable? | Meaning | Pipeline exit code |
|----------|-----------|---------------|---------|--------------------|
| `queued` | no | no | Accepted, awaiting a worker. | — |
| `running` | no | no | Pipeline executing. | — |
| `succeeded` | yes | **yes** | All artifacts produced **and** validated. | `0` |
| `unvalidated` | yes | **yes** | Artifacts produced but **not** fully validated (best-effort / fail-open). | `3` |
| `failed` | yes | no | Domain failure — datasheet unparseable / fail-closed. | `1` |
| `error` | yes | no | Internal error (a bug). | `2` |
| `timeout` | yes | no | Exceeded `API_JOB_TIMEOUT`. | (killed) |

Downloadable set = `{succeeded, unvalidated}`.

---

## Generated artifacts

Every successful job yields up to four files (order = display order):

| Suffix | MIME | What it is |
|--------|------|------------|
| `_schematic.glb` | `model/gltf-binary` | Schematic symbol (functional pin grouping, SYM rules). |
| `_footprint.glb` | `model/gltf-binary` | PCB footprint (pads, silk, fab outline, courtyard). |
| `_body.glb` | `model/gltf-binary` | 3D component body. |
| `_body.step` | `application/step` | 3D body as STEP (CAD interchange). |

---

## HTTP status codes

| Code | When |
|------|------|
| `200` | `/health`, `/parse` success, artifact download. |
| `202` | `/jobs` accepted. |
| `400` | Missing file, or non-PDF upload. |
| `404` | Unknown `job_id` or artifact `name`. |
| `409` | Artifact requested but job not in a downloadable state. |
| `413` | Upload exceeds the size limit (25 MB default). |
| `422` | `/parse` — datasheet could not be parsed (domain failure). |
| `500` | `/parse` — internal error. |
| `503` | `/parse` — too many concurrent parses (retry, or use `/jobs`). |
| `504` | `/parse` — pipeline exceeded the timeout. |

---

## Environment variables

| Var | Default | Effect |
|-----|---------|--------|
| `API_JOBS_DIR` | `api_jobs` | Per-job work dirs. |
| `API_MAX_UPLOAD_MB` | `25` | Upload size cap. |
| `API_MAX_CONCURRENT_PARSE` | `2` | Concurrent sync `/parse` builds. |
| `API_JOB_TIMEOUT` | `360` | Per-job wall-clock timeout (s). |
| `API_WORKERS` | `4` | Async worker threads. |
| `FASTCHAT_API_KEY` | — | **Required** for the LLM extraction step of a real parse. |
