from __future__ import annotations

from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles
from starlette.types import Scope


class SPAStaticFiles(StaticFiles):
    """StaticFiles that falls back to index.html for unmatched paths.

    Starlette's built-in html=True only falls back to 404.html, not index.html,
    so deep-link navigation (e.g. /market/some-uuid typed directly in the browser)
    would return 404 without this override. This subclass catches the 404 from the
    parent and re-serves index.html so React Router can handle the route client-side.

    Exact files (JS bundles, CSS, favicon.svg, icons.svg) are served normally from
    the mounted directory; only truly missing paths fall through to index.html.
    """

    async def get_response(self, path: str, scope: Scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise
