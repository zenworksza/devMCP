from __future__ import annotations

"""Stub for the future Gemini broker repair.

Gemini routed execution is intentionally disabled for now. The next repair
should replace this stub with a dedicated broker/service that owns the ACP
session lifecycle and emits raw protocol transcripts for debugging.
"""


def submit_prompt(prompt: str, timeout_seconds: int = 95) -> str:
    raise RuntimeError(
        "Gemini sidecar is disabled pending ACP broker repair. "
        "Re-enable this module only after the dedicated Gemini broker is implemented."
    )
