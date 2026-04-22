from __future__ import annotations

import os

from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

# Path prefixes that must never fall back to index.html.
# These are URL segments after the mount root ("/"), so no leading slash.
_API_PREFIXES = ("api/", "static/", "assets/")


def _is_browser_route(path: str) -> bool:
    """Return True only for paths that look like SPA client-side routes.

    Paths with a file extension (.js, .css, .svg, .png …) are asset requests —
    if the file is missing the caller should get a real 404, not index.html.
    Paths under api/, static/, or assets/ are never browser routes regardless
    of extension, so typo'd API URLs stay 404 JSON instead of returning HTML.

    Starlette's StaticFiles.get_path() uses os.path.join() which produces
    backslash separators on Windows. Normalise before the prefix check so
    behaviour is identical on Linux (production) and Windows (dev/CI).
    """
    normalised = path.replace("\\", "/")
    if normalised.startswith(_API_PREFIXES):
        return False
    _, ext = os.path.splitext(path)
    return ext == ""


class SPAStaticFiles(StaticFiles):
    """StaticFiles that falls back to index.html for SPA client routes only.

    Starlette 0.47 html=True does not fall back to root index.html for
    unmatched paths; it only serves directory/index.html. This subclass adds
    the SPA fallback while keeping real 404s for:
      - extension-bearing paths  (/assets/chunk.js, /favicon.xyz)
      - API namespaces           (/api/…, /static/…, /assets/…)
    """

    async def get_response(self, path: str, scope: Scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code == 404 and _is_browser_route(path):
                return await super().get_response("index.html", scope)
            raise
