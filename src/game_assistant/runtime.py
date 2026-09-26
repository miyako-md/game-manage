"""Project-owned local runner used by scripts/start.ps1 (never a public listener)."""
import argparse
import asyncio
from contextlib import suppress
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys


def build_app(sandbox_dir: Path | None = None):
    from game_assistant.api import create_app
    if sandbox_dir is None:
        return create_app()
    from game_assistant.config import Settings

    sandbox_dir.mkdir(parents=True, exist_ok=True)
    # Explicit values outrank GA_* environment variables. Never load config.toml
    # or a personal credential store in the process verification sandbox.
    values = {name: field.get_default(call_default_factory=True)
              for name, field in Settings.model_fields.items()}
    values.update(db_path=str(sandbox_dir / "assistant.db"),
                  auth_store_path=str(sandbox_dir / "credentials.json"),
                  wuwa_enabled=False, lol_enabled=False, nte_enabled=False, endfield_enabled=False,
                  notify_send_key="")
    return create_app(settings=Settings(**values), start_scheduler=False)


async def _serve(app, port: int, runtime_dir: Path, runtime_id: str) -> None:
    import uvicorn

    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=port, log_config=None,
        access_log=False, timeout_graceful_shutdown=8,
    ))

    async def watch_stop():
        request_path = runtime_dir / "stop.json"
        while not server.should_exit:
            try:
                request = json.loads(request_path.read_text(encoding="utf-8"))
                if isinstance(request, dict) and request.get("runtime_id") == runtime_id:
                    logging.info("Verified local stop request; beginning graceful shutdown.")
                    server.should_exit = True
                    return
            except (OSError, UnicodeError, ValueError):
                # Missing, incomplete and stale files are harmless. No file data
                # is logged; only the matching run may request shutdown.
                pass
            await asyncio.sleep(0.25)

    watcher = asyncio.create_task(watch_stop())
    try:
        await server.serve()
    finally:
        watcher.cancel()
        with suppress(asyncio.CancelledError):
            await watcher


class _LogStream:
    def __init__(self, level):
        self.level = level

    def write(self, message):
        if message.strip():
            logging.getLogger("runtime.console").log(self.level, message.rstrip())

    def flush(self):
        pass

    def isatty(self):
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--runtime-id", required=True)
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--sandbox", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    runtime_dir = args.runtime_dir.resolve()
    if not runtime_dir.is_relative_to(root / "data" / "runtime"):
        parser.error("runtime directory must be inside this project's data/runtime")
    if args.port != 8010 and not args.sandbox:
        parser.error("alternate ports require --sandbox")
    if args.sandbox and args.port == 8010:
        parser.error("sandbox requires a separate port")
    os.chdir(root)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(runtime_dir / "service.log", maxBytes=2 * 1024 * 1024,
                                  backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    # HTTPX INFO includes complete request URLs; ServerChan embeds the push
    # credential in its URL path. Transport diagnostics can include headers.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    # Access URLs can contain caller-provided query secrets; suppress access logs.
    sys.stdout = _LogStream(logging.INFO)
    sys.stderr = _LogStream(logging.ERROR)
    try:
        handshake = {"pid": os.getpid(), "root": str(root), "port": args.port,
                     "runtime_id": args.runtime_id}
        ready = runtime_dir / "ready.json"
        staged = ready.with_suffix(".tmp")
        staged.write_text(json.dumps(handshake), encoding="utf-8")
        staged.replace(ready)
        app = build_app(runtime_dir / "sandbox-data" if args.sandbox else None)
        asyncio.run(_serve(app, args.port, runtime_dir, args.runtime_id))
    except Exception as exc:
        # Validation exception text can contain setting values. Do not log it.
        logging.error("Local runtime failed (%s); verify dependencies/configuration.",
                      type(exc).__name__)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
