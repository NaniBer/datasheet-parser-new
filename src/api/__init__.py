"""
HTTP API layer.

A thin async wrapper over the existing CLI pipeline (``python -m src.main``).
Callers upload a PDF datasheet, the job runs the validated pipeline in an
isolated subprocess, and the generated GLB/STEP artifacts are served back as
downloads. See ``docs/plans/2026-08-21-http-api-design.md`` for the design.
"""
