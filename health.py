"""Health command for the Centas extension (no network)."""

from __future__ import annotations

import json


def check_health() -> dict[str, object]:
    from runtime.catalog import OPERATION_IDS, WRITE_OPERATION_IDS
    from runtime.connection import BASE_URL
    from runtime.reference import SPECIFICATION

    return {
        "extension_id": "flowsteward.centas",
        "ok": True,
        "status": "healthy",
        "api": BASE_URL,
        "specification_sha256": SPECIFICATION["sha256"],
        "declared_operations": len(OPERATION_IDS),
        "effect_operations": len(WRITE_OPERATION_IDS),
    }


if __name__ == "__main__":
    print(json.dumps(check_health(), separators=(",", ":"), sort_keys=True))
