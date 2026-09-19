"""Local API boundary against cross-site writes and DNS rebinding reads."""
from ipaddress import ip_address
from urllib.parse import urlsplit

from starlette.responses import JSONResponse


def _authority(value):
    # Parse the raw Host, never request.url: malformed IPv6 must fail closed,
    # and credentials, paths or a host suffix must not become a trusted host.
    if not value or any(c.isspace() or ord(c) < 32 for c in value):
        return None
    try:
        parsed = urlsplit('//' + value)
        if (not parsed.hostname or parsed.username is not None or parsed.password is not None
                or parsed.path or parsed.query or parsed.fragment or '\\' in value):
            return None
        return parsed.hostname.lower(), parsed.port
    except ValueError:
        return None


def _origin(value):
    if not value or any(c.isspace() or ord(c) < 32 for c in value):
        return None
    try:
        parsed = urlsplit(value)
        authority = _authority(parsed.netloc)
        if (parsed.scheme not in ('http', 'https') or authority is None
                or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
            return None
        host, port = authority
        if port is None:
            port = 443 if parsed.scheme == 'https' else 80
        return parsed.scheme, host, port
    except ValueError:
        return None


def _loopback(host):
    if host == 'localhost':
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def install_api_security(app, settings):
    origins = {_origin(value) for value in settings.auth_allowed_origins}
    origins.discard(None)
    hosts = {origin[1] for origin in origins}

    @app.middleware('http')
    async def protect_api(request, call_next):
        path = request.scope['path']
        if path != '/api' and not path.startswith('/api/'):
            return await call_next(request)
        host_values = request.headers.getlist('host')
        authority = _authority(host_values[0]) if len(host_values) == 1 else None
        allowed = authority is not None and (_loopback(authority[0]) or authority[0] in hosts)
        origin_values = request.headers.getlist('origin')
        if origin_values:
            allowed = allowed and len(origin_values) == 1 and _origin(origin_values[0]) in origins
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            allowed = allowed and request.headers.getlist('x-game-assistant') == ['1']
        if allowed:
            response = await call_next(request)
        else:
            response = JSONResponse({'detail': '请从本机游戏助手页面操作'}, status_code=403)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response
