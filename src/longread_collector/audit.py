from __future__ import annotations


def record_auxiliary_error(store: object, stage: str, exc: Exception) -> str:
    message = f"{stage}:{type(exc).__name__}:{exc}"[:600]
    errors = list(getattr(store, "_v04_audit_errors", []))
    errors.append(message)
    setattr(store, "_v04_audit_errors", errors[-10:])
    return message
