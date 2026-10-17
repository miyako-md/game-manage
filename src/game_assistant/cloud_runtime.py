"""Dedicated cloud runtime. Explicit config, one worker, loopback only."""
import argparse
from dataclasses import dataclass
from ipaddress import ip_address
from pathlib import Path
import sqlite3
import sys
import tomllib

from .config import Settings


class RuntimeConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class CloudRuntime:
    settings: Settings
    host: str = '127.0.0.1'
    port: int = 8020
    frontend_dist: Path | None = None


def load_runtime(path):
    try:
        config = Path(path).absolute()
        if any(p.is_symlink() for p in (config,*config.parents)) or not config.is_file():
            raise ValueError()
        config = config.resolve(strict=True)
        data = tomllib.loads(config.read_text(encoding='utf-8'))
        runtime = data.pop('runtime', {})
        if set(runtime) - {'host','port','frontend_dist'}:
            raise RuntimeConfigurationError('unknown_runtime_setting')
        host, port = runtime.get('host', '127.0.0.1'), runtime.get('port', 8020)
        if not ip_address(host).is_loopback:
            raise RuntimeConfigurationError('loopback_required')
        if type(port) is not int or not 1024 <= port <= 65535:
            raise RuntimeConfigurationError('invalid_runtime_port')
        required = {'cloud_db_path','cloud_data_root','cloud_credentials_key_path','cloud_allowed_origins'}
        if not required <= data.keys() or data.get('cloud_accounts_enabled') is not True:
            raise RuntimeConfigurationError('explicit_cloud_configuration_required')
        from .api_security import _origin
        origins=[_origin(value) for value in data['cloud_allowed_origins']]
        if not origins or any(origin is None or origin[0]!='https' for origin in origins):
            raise RuntimeConfigurationError('https_origins_required')
        for field in ('cloud_db_path','cloud_data_root','cloud_credentials_key_path','db_path',
                      'system_update_state_dir','system_update_install_root'):
            if field in data and data[field]:
                candidate = Path(data[field])
                if not candidate.is_absolute():
                    candidate = config.parent / candidate
                if any(p.is_symlink() for p in (candidate,*candidate.parents)):
                    raise RuntimeConfigurationError('symlink_path_rejected')
                data[field] = str(candidate.resolve())
        root = Path(data['cloud_data_root'])
        key = Path(data['cloud_credentials_key_path'])
        if key.is_relative_to(root) or root.is_relative_to(key) or key == Path(data['cloud_db_path']):
            raise RuntimeConfigurationError('key_must_be_external')
        from .auth.store import CredentialStore
        CredentialStore('unused', key_path=key)._grant_key()
        # Never search/import local config or consume local single-user secrets.
        data.setdefault('db_path', str(config.parent / '.unused-local.db'))
        settings = Settings(**data)
        if 'lol_enabled' in data and data['lol_enabled']:
            raise RuntimeConfigurationError('local_service_configuration_forbidden')
        from .auth.service import FIELDS
        secret_fields = {field for mapping in FIELDS.values() for field in mapping.values()}
        secret_fields.discard('wuwa_token_source')
        secret_fields.update({'wuwa_app_token','notify_send_key','auth_store_path'})
        if any(getattr(settings, field) for field in secret_fields):
            raise RuntimeConfigurationError('local_credentials_forbidden')
        settings.lol_enabled = False
        dist = runtime.get('frontend_dist')
        if settings.system_update_enabled and settings.system_update_install_root:
            from .system_update_version import source_root, release_root_matches
            running_root = source_root()
            if release_root_matches(running_root, settings.system_update_install_root):
                # Versioned releases must serve their own assets, not the previous config's dist.
                dist = str(running_root / 'frontend' / 'dist')
        if dist:
            candidate = Path(dist)
            candidate = candidate if candidate.is_absolute() else config.parent / candidate
            if any(path.is_symlink() for path in (candidate,*candidate.parents)):
                raise RuntimeConfigurationError('symlink_path_rejected')
            dist = candidate.resolve()
            if dist == root or dist.is_relative_to(root) or root.is_relative_to(dist):
                raise RuntimeConfigurationError('frontend_data_overlap')
        return CloudRuntime(settings, host, port, dist)
    except RuntimeConfigurationError:
        raise
    except Exception:
        raise RuntimeConfigurationError('invalid_cloud_configuration') from None


def build_app(runtime, *, start_scheduler=True):
    from .cloud_app import create_cloud_app, allow_cloud_route
    app = create_cloud_app(runtime.settings, start_scheduler=start_scheduler)
    from .system_update_version import capture_version
    version = capture_version(frontend_dist=runtime.frontend_dist)
    app.state.system_update.version = version
    app.state.running_version = version
    from fastapi import Request
    from starlette.responses import JSONResponse
    @app.get('/internal/operations/health')
    async def operations_health(request: Request):
        principal = request.state.identity_session.principal
        try:
            if not principal.is_admin or not ip_address(request.client.host).is_loopback:
                return JSONResponse({'detail':'operations_access_denied'},status_code=403)
        except ValueError:
            return JSONResponse({'detail':'operations_access_denied'},status_code=403)
        try:
            with app.state.identity.store.connect() as db:
                db.execute('SELECT 1').fetchone()
            app.state.accounts.connection.execute('SELECT 1').fetchone()
            app.state.store._conn.execute('SELECT 1').fetchone()
        except sqlite3.Error:
            return JSONResponse({'status':'degraded','databases':'unavailable'},status_code=503)
        scheduler = app.state.scheduler
        running = scheduler._running and (scheduler._loop is None or not scheduler._loop.done())
        return JSONResponse({'status':'ok' if running else 'degraded','databases':'ok',
                             'scheduler':'running' if running else 'stopped'},status_code=200 if running else 503)
    allow_cloud_route(app, '/internal/operations/health', ['GET'])
    if runtime.frontend_dist:
        from .cloud_web_ui import install_cloud_ui
        install_cloud_ui(app, runtime.frontend_dist)
    return app


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, help='Explicit cloud TOML file; no default/local config discovery')
    parser.add_argument('--check', action='store_true', help='Validate configuration/key/static files without opening database or starting service')
    args = parser.parse_args(argv)
    try:
        runtime = load_runtime(args.config)
        if args.check:
            if runtime.frontend_dist:
                from .cloud_web_ui import validate_dist
                validate_dist(runtime.frontend_dist)
            print('cloud_configuration_valid')
            return 0
        import uvicorn
        uvicorn.run(build_app(runtime), host=runtime.host, port=runtime.port, workers=1,
            proxy_headers=False, access_log=False, server_header=False, limit_concurrency=64,
            timeout_keep_alive=5, timeout_graceful_shutdown=30)
        return 0
    except (RuntimeConfigurationError, ValueError, OSError, sqlite3.Error):
        print('cloud_startup_failed', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
