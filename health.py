"""Health command for the Centas extension (no network)."""

from __future__ import annotations

import json


def check_health() -> dict[str, object]:
    from runtime.catalog import OPERATION_IDS, WRITE_OPERATION_IDS
    from runtime.connection import BASE_URL
    from runtime.reference import SOURCE

    return {
        "extension_id": "flowsteward.centas",
        "ok": True,
        "status": "healthy",
        "api": BASE_URL,
        "documentation_sha256": SOURCE["sha256"],
        "declared_operations": len(OPERATION_IDS),
        "write_operations": len(WRITE_OPERATION_IDS),
    }


if __name__ == "__main__":
    print(json.dumps(check_health(), separators=(",", ":"), sort_keys=True))
