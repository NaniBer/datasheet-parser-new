# Datasheet Parser API — Input / Output Schema

HTTP API (`src/api/`, FastAPI) that takes a **PDF datasheet** and returns the
generated **3D artifacts** (schematic symbol, PCB footprint, 3D body) as GLB +
STEP files.

- **Production base URL:** `https://datasheet-parser.ideeza.com`
- **Base URL (local):** `http://127.0.0.1:8000`
- **Interactive docs (Swagger):** `/docs` — **VPN-only** in production; open locally at `http://127.0.0.1:8000/docs`. Raw schema at `/openapi.json`.
- **Version:** `0.1.0`
- **Auth:** send header **`apikey: <KEY>`** on **every** request except `GET /health` (the only open route). **Never commit the key** — pass it via an env var / secret.

### Auth + the `part_number` requirement (read first)

```bash
export DP_KEY='…your key…'          # do NOT hard-code / commit this
export DP_URL='https://datasheet-parser.ideeza.com'
```

- **Always send `part_number`.** Without it the footprint step fails on a missing
  reference file `/app/2d.glb` and the API returns **`422`**.
- **Deployed-image caveat.** `part_number` alone does **not** rescue every part on
  the current deploy — some still `422` on the missing `/app/2d.glb` reference until
  the deploy bundles it (or the check is made fail-open).
- **Limits:** **25 MB** upload (`413`), **2** concurrent parses (`503`), **360 s**
  per job (`504`). `POST /parse` is ~25 s for a small part. (Env-tunable — see below.)

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

**Error body shape.** Every non-2xx response (except raw binary downloads) is JSON — FastAPI's standard `{ "detail": ... }` (a string for app errors, or a list for request-validation errors).

---

## Per-endpoint reference (schema · errors · example in → out)

### 1. `GET /health`
Liveness probe. No input, no `apikey`. Always `{ "status": "ok" }` (`200`) if up.

```bash
curl "$DP_URL/health"
```

---

### 2. `POST /jobs` — async submit
Accepts the upload, registers a job, returns immediately with a `job_id`.

- **Request** (`multipart/form-data`): `file` (binary PDF, **required**) + `part_number` (string, optional — disambiguates a multi-part datasheet).
- **Output** — `202` `JobCreated`: `{ "job_id": string, "status": string }`
- **Errors:** `400` (no file / non-PDF), `413` (> 25 MB), `422` (malformed multipart / missing field).

```bash
curl -s -X POST "$DP_URL/jobs" \
  -H "apikey: $DP_KEY" \
  -F "file=@pdfs/74HC595_TI.pdf" \
  -F "part_number=SN74HC595"           # ALWAYS send part_number
# → 202 { "job_id": "60333c6d…", "status": "queued" }
```

---

### 3. `GET /jobs/{job_id}` — poll status
Returns the job's current state and, once terminal & downloadable, its artifact list.

- **Request:** path param `job_id` (hex string from step 2). No body.
- **Output** — `200` `JobStatus` (fields defined under **Response objects** below).
- **Errors:** `404` (unknown `job_id`).

```bash
curl -s -H "apikey: $DP_KEY" "$DP_URL/jobs/60333c6d…"
```
```json
{
  "job_id": "60333c6d…",
  "status": "succeeded",
  "validated": true,
  "artifacts": [
    { "name": "output_schematic.glb", "type": "model/gltf-binary", "size": 2823960,
      "download_url": "/jobs/60333c6d…/artifacts/output_schematic.glb" },
    { "name": "output_footprint.glb", "type": "model/gltf-binary", "size": 1215072, "download_url": "…" },
    { "name": "output_body.glb", "type": "model/gltf-binary", "size": 534552, "download_url": "…" },
    { "name": "output_body.step", "type": "application/step", "size": 847560, "download_url": "…" }
  ],
  "reason": null
}
```
While running: `status: "running"`, `validated: null`, `artifacts: []`. On a domain
failure: `status: "failed"`, `validated: false`, `reason` carries the cause.

---

### 4. `GET /jobs/{job_id}/artifacts/{name}` — download one file
Streams a single artifact. `name` must be an exact entry from the `artifacts` list (acts as an allowlist).

- **Output:** raw bytes, `Content-Type` = the artifact MIME, `Content-Disposition: attachment; filename="<name>"`.
- **Errors:** `404` (unknown job/artifact), `409` (job not in a downloadable state).

```bash
curl -s -OJ -H "apikey: $DP_KEY" \
  "$DP_URL/jobs/60333c6d…/artifacts/output_schematic.glb"
```

---

### 5. `POST /parse` — synchronous parse
Blocks for the whole pipeline (~1–2 min) and streams back **all** artifacts as one ZIP.

- **Request:** identical to `POST /jobs` (`file` + optional `part_number`).
- **Output:** `200` `application/zip`, with headers `Content-Disposition: attachment; filename="<pdf-stem>_artifacts.zip"`, `X-Job-Status`, `X-Validated`.
- **Errors:** `400` (no file / non-PDF), `413` (> 25 MB), `422` (unparseable datasheet), `500` (internal error), `503` (too many concurrent parses), `504` (timeout).

```bash
curl -s -X POST "$DP_URL/parse" \
  -H "apikey: $DP_KEY" \
  -F "file=@pdfs/AMS1117.pdf" -F "part_number=AMS1117" \
  -OJ -D headers.txt                   # ZIP + response headers
```
The verdict is in the response headers:
```
x-job-status: succeeded
x-validated: true
```

---

## Response objects

**`JobStatus`** (`GET /jobs/{job_id}`):

| Field | Type | Meaning |
|-------|------|---------|
| `job_id` | string | The job id. |
| `status` | string | Lifecycle state — see the table below. |
| `validated` | bool \| null | `null` until terminal. Then `true` = fully validated run, `false` = best-effort (produced but unvalidated). |
| `artifacts` | `Artifact[]` | Empty until the job produces files. |
| `reason` | string \| null | Actionable message (tail of pipeline output, ≤2000 chars) for `failed`/`error`/`timeout`; `null` otherwise (including `unvalidated` — see Validation below). |

**`Artifact`** (an entry in `artifacts`):

| Field | Type | Meaning |
|-------|------|---------|
| `name` | string | Filename; also the `{name}` download path segment (allowlist — traversal names 404). |
| `type` | string | MIME: `model/gltf-binary` (GLB) or `application/step` (STEP). |
| `size` | int | Size in bytes. |
| `download_url` | string | Relative URL: `/jobs/{job_id}/artifacts/{name}`. |

`POST /jobs` returns `JobCreated`: `{ "job_id": string, "status": "queued" }`.

---

## Job lifecycle (`status` values)

| `status` | Terminal? | Downloadable? | Meaning | Exit code |
|----------|-----------|---------------|---------|-----------|
| `queued` | no | no | Accepted, awaiting a worker. | — |
| `running` | no | no | Pipeline executing. | — |
| `succeeded` | yes | **yes** | All artifacts produced **and** validated. | `0` |
| `unvalidated` | yes | **yes** | Artifacts produced but **not** validated (best-effort / fail-open). | `3` |
| `failed` | yes | no | Domain failure — datasheet unparseable / fail-closed. | `1` |
| `error` | yes | no | Internal error (a bug). | `2` |
| `timeout` | yes | no | Exceeded `API_JOB_TIMEOUT`. | (killed) |

Downloadable set = `{succeeded, unvalidated}`.

---

## Validation & uncertainty — what `validated` means

`validated` (and the `unvalidated` status / `X-Validated` header) tells you whether
the pipeline could **verify the extracted pinout against the datasheet itself**, not
just whether a file was produced. `succeeded` (`validated: true`) and `unvalidated`
(`validated: false`) return the **same downloadable artifacts** — the difference is
confidence.

### What the pipeline does when it's unsure

An **abstention gate** tags every pin with its provenance (does its **number** appear
in the datasheet? does its **name**?) and classifies the pinout:

| Signature | Detection | Default (fail-open) | `--strict` (fail-closed) |
|-----------|-----------|---------------------|--------------------------|
| **Invention** — made up, not read from the doc | < 50% of pin **numbers** appear in the datasheet | `validated: false` (`unvalidated`) | Refuse — `failed` |
| **Hallucinated name(s)** — real pinout with stray invented pins | ≥ 60% grounded, but some pin **name** appears nowhere | `validated: false` (`unvalidated`) | Refuse — `failed` |
| **Unverifiable / graphical** — connection diagram with a garbled text layer | Low grounding, but pin numbers *are* present | **Not refused** — handed to the vision path; result ships | Same — not refused |

The thresholds are deliberate: a *correct* graphical part (e.g. AD712) grounds at only
~25% because its labels are vector art, so refusing on low grounding would wrongly
reject every picture-based pinout.

### Fail-open is the default

The API **never refuses on a validation gate** by default — it emits the best-effort
result marked `unvalidated` (`validated: false`, exit `3`). Pass **`--strict`** (CLI) to
fail closed instead (gate raises → `failed`, exit `1`, no artifacts). Use `validated` to
gauge trust, not whether a result exists.

### Where the reason lives

- **API:** `JobStatus.reason` carries the cause for `failed`/`error`/`timeout`. For an
  **`unvalidated`** result `reason` is `null` — the verdict is the flag only.
- **Inside the GLB:** the full cause is stamped on `scene.extras` as `validated: false`
  + `validationErrors: [...]` (e.g. *"1 pin name(s) appear nowhere in the datasheet
  ('V-') … likely hallucinated"*), readable straight off the artifact. Platforms
  typically **suppress or flag** `validated: false` parts in their 2D/3D views.

### Caveat — "validated" is a text-grounding check, not proof of correctness

`validated: true` means every pin name **appears** in the datasheet — **not** that each
name sits on the **correct pin number**. A pinout read from a connection diagram can be
internally scrambled yet fully grounded, so it can pass as `validated: true` while the
number→name mapping is wrong. This is why the pipeline cross-checks table-less graphical
parts against the rendered diagram via the vision path rather than trusting grounding.

---

## Generated artifacts

Every downloadable job yields up to four files (order = display order):

| Suffix | MIME | What it is |
|--------|------|------------|
| `_schematic.glb` | `model/gltf-binary` | Schematic symbol (functional pin grouping, SYM rules). |
| `_footprint.glb` | `model/gltf-binary` | PCB footprint (pads, silk, fab outline, courtyard). |
| `_body.glb` | `model/gltf-binary` | 3D component body. |
| `_body.step` | `application/step` | 3D body as STEP (CAD interchange). |

---

## Environment variables

| Var | Default | Effect |
|-----|---------|--------|
| `API_JOBS_DIR` | `api_jobs` | Per-job work dirs. |
| `API_MAX_UPLOAD_MB` | `25` | Upload size cap (`413` over). |
| `API_MAX_CONCURRENT_PARSE` | `2` | Concurrent sync `/parse` builds (`503` over). |
| `API_JOB_TIMEOUT` | `360` | Per-job wall-clock timeout in s (`504` over). |
| `API_WORKERS` | `4` | Async worker threads. |
| `FASTCHAT_API_KEY` | — | **Required** for the LLM extraction step of a real parse. |
