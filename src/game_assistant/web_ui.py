"""Optional local SPA hosting; install only after registering all API routes."""
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse


def install_web_ui(app: FastAPI, dist_dir: str | Path | None = None) -> None:
    dist = (Path(dist_dir) if dist_dir is not None else
            Path(__file__).resolve().parents[2] / "frontend" / "dist").resolve()
    index = dist / "index.html"
    if not index.is_file():
        return

    @app.api_route("/{path:path}", include_in_schema=False,
                   methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT"])
    async def web_ui(path: str, request: Request):
        # Reserve the complete API namespace, including extensionless misses.
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404)
        if request.method not in {"GET", "HEAD"}:
            raise HTTPException(status_code=405, headers={"Allow": "GET, HEAD"})
        # Reject Windows separators, drives/ADS, dot segments and symlink escapes.
        if "\\" in path or ":" in path or "\x00" in path or ".." in path.split("/"):
            raise HTTPException(status_code=404)
        target = (dist / path).resolve()
        if not target.is_relative_to(dist):
            raise HTTPException(status_code=404)
        if target.is_file():
            headers = {"Cache-Control": "no-cache"} if target == index else None
            return FileResponse(target, headers=headers)
        if path == "assets" or path.startswith("assets/") or Path(path).suffix:
            raise HTTPException(status_code=404)
        # Resolve again: a replaced index symlink must not expose an outside file.
        if not index.resolve().is_relative_to(dist) or not index.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
