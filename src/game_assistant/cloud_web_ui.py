"""Public static cloud UI only. Data/API/internal paths never reach dist."""
from pathlib import Path

from fastapi import HTTPException
from starlette.responses import FileResponse


# Renderer metadata is read from disk only, never published as a UI route.
_PRIVATE_BUILD_FILES = frozenset({'render-font.json'})


def validate_dist(value):
    dist = Path(value).absolute()
    if any(path.is_symlink() for path in (dist,*dist.parents)):
        raise ValueError('Unsafe static dist')
    dist = dist.resolve(strict=True)
    if not dist.is_dir() or 'data-service-mode="cloud"' not in (dist / 'index.html').read_text(encoding='utf-8'):
        raise ValueError('An explicit cloud build is required')
    for path in dist.rglob('*'):
        if path.is_symlink() or not path.resolve().is_relative_to(dist):
            raise ValueError('Unsafe static dist')
        if (path.is_file() and path.relative_to(dist).as_posix() not in
                {'game-icons/sources.json', 'build-info.json', *_PRIVATE_BUILD_FILES}
                and path.suffix.lower() not in {'.html','.js','.css','.svg','.png','.jpg','.jpeg','.webp','.gif','.ico','.woff','.woff2','.ttf'}):
            raise ValueError('Unexpected static artifact')
    return dist


def install_cloud_ui(app, value):
    from .cloud_app import allow_cloud_route
    dist = validate_dist(value)

    async def serve(path=''):
        if (path in _PRIVATE_BUILD_FILES
                or path.split('/')[0].lower() in {'api','internal','data','private','.well-known'}
                or any(part.startswith('.') for part in path.split('/')) or '\\' in path or ':' in path):
            raise HTTPException(404, 'route_not_available')
        target = dist / (path or 'index.html')
        if any(p.is_symlink() for p in (target,*target.parents)) or not target.resolve().is_relative_to(dist):
            raise HTTPException(404, 'route_not_available')
        if not target.is_file():
            raise HTTPException(404, 'route_not_available')
        return FileResponse(target)

    def endpoint(relative):
        async def fixed_file():
            return await serve(relative)
        return fixed_file

    # Exact files only: account routes are installed during lifespan, after
    # this helper. A catch-all route would steal those future API requests.
    paths = [('', '/')] + [(p.relative_to(dist).as_posix(), '/' + p.relative_to(dist).as_posix())
        for p in sorted(dist.rglob('*')) if p.is_file()
        and p.relative_to(dist).as_posix() not in _PRIVATE_BUILD_FILES]
    for relative, route in paths:
        if route.split('/')[1].lower() in {'api','internal','data','private'}:
            raise ValueError('Unsafe static path')
        app.add_api_route(route, endpoint(relative), methods=['GET','HEAD'])
        allow_cloud_route(app, route, ['GET','HEAD'], access='public')
