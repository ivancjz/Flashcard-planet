# backend/app/core/boundary_check.py
"""
Boundary rules for the DataService layer.

New Bot code and new Web route code MUST NOT import from services/ or models/
directly. All data access goes through DataService.

Whitelist exceptions (safe to import anywhere):
  - core.permissions
  - core.response_types
  - core.config
  - core.data_service (the gateway itself)

To enforce in CI, scan new .py files for forbidden patterns:
  grep -rn "from backend.app.services\|from backend.app.models" bot/ \
    | grep -v "# boundary-ok"

Add `# boundary-ok` comment on any intentional exception.
"""

BOUNDARY_RULES = {
    "forbidden_direct_imports": [
        "backend.app.models",
        "backend.app.services",
    ],
    "must_go_through": [
        "backend.app.core.data_service.DataService",
    ],
    "whitelist": [
        "backend.app.core.permissions",
        "backend.app.core.response_types",
        "backend.app.core.config",
        "backend.app.core.data_service",
    ],
    "boundary_ok_marker": "# boundary-ok",
}
