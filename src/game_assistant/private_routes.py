"""Explicit cloud private routes. The local API is never mounted here."""
import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from starlette.responses import JSONResponse

from .accounts.store import AccountNotFoundError
from .identity.dependencies import require_user
from .models import Capability
from .endfield_blueprints import BlueprintInput, BlueprintStore
from .endfield_gacha import EndfieldGachaStore
from .endfield_skland import EndfieldSklandService
from .adapters.endfield.skland_client import SklandError
from .nte_gacha import GachaError, GachaStore as NteStore
from .wuwa_gacha import GachaStore as WuwaStore, fetch_official
from .wuwa_history import WuwaHistory

PREFIX='/api/accounts/{account_id}/roles/{role_id}'


class PrivateRoutes:
    def __init__(self,accounts,runtime,private_root,snapshots=None):
        self.accounts,self.runtime,self.private_root,self.snapshots=accounts,runtime,private_root,snapshots
        self._ledgers={}
        self._skland={}
        self.routes=[]
        self.accounts._listeners.append(self.invalidate)

    def scope_for(self,game,provider=None):
        async def resolve(account_id:str,role_id:str,principal=Depends(require_user)):
            scope=self.accounts.require_scope(principal,account_id,role_id)
            info=self.accounts.describe(scope)
            if info['game']!=game or (provider is not None and info['provider']!=provider):
                raise AccountNotFoundError()
            return scope
        return resolve

    def ledger(self,scope,kind):
        info=self.accounts.describe(scope)
        key=(scope,kind)
        if key not in self._ledgers:
            cls={'nte':NteStore,'wuwa_gacha':WuwaStore,'wuwa_history':WuwaHistory,
                 'endfield_gacha':EndfieldGachaStore,'blueprints':BlueprintStore}[kind]
            self._ledgers[key]=cls.for_scope(scope,self.private_root,role_uid=info['game_uid'],server_id=info['server'])
        return self._ledgers[key]

    def skland(self,scope):
        info=self.accounts.describe(scope)
        previous=self._skland.get(scope)
        if previous and previous[0]==info['version']:
            return previous[2]
        if previous:
            previous[2].close()
        session=self.accounts.credentials.load_grant(scope.user_id,info['grant_id'])
        service=EndfieldSklandService.for_scope(scope,
            {**session,'role_id':info['game_uid'],'server_id':info['server']})
        self._skland[scope]=(info['version'],info['grant_id'],service)
        return service

    def cached_skland(self,scope):
        """Read already observed views without loading credentials or a service."""
        info=self.accounts.describe(scope)
        cached=self._skland.get(scope)
        if cached is None or cached[0]!=info['version']:
            return {}
        return cached[2].cached_views(scope)

    def invalidate(self,user_id,grant_id):
        for scope,value in list(self._skland.items()):
            if scope.user_id==user_id and value[1]==grant_id:
                value[2].close()
                self._skland.pop(scope,None)

    def clear_private(self,scope):
        """Post-commit callback: drop snapshots/caches; retain historical ledgers."""
        if self.snapshots is not None:
            self.snapshots.clear_scoped(scope)
        value=self._skland.pop(scope,None)
        if value:
            value[2].close()

    def close(self):
        if self.invalidate in self.accounts._listeners:
            self.accounts._listeners.remove(self.invalidate)
        for value in self._skland.values():
            value[2].close()
        self._skland.clear()
        for ledger in self._ledgers.values():
            ledger.close()
        self._ledgers.clear()

    def include(self,app,router):
        app.include_router(router)
        for route in router.routes:
            category='private_query' if route.methods<= {'GET','HEAD'} else 'private_modify'
            self.routes.append((route.path,frozenset(route.methods),category))

    def allowlist(self,app):
        """Explicit opt-in after the cloud boundary has been installed."""
        from .cloud_app import allow_cloud_route
        for path,methods,_ in self.routes:
            allow_cloud_route(app,path,methods,access='user')


async def _body(request,maximum=8*1024*1024):
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>maximum:
            raise HTTPException(413,'request_too_large')
    try:
        value=json.loads(raw)
    except (ValueError,UnicodeError,RecursionError):
        raise HTTPException(422,'invalid_input') from None
    if not isinstance(value,dict):
        raise HTTPException(422,'invalid_input')
    return value


def _options(body):
    result={}
    for name in ('latest_confirmed','continuity_confirmed','identity_confirmed'):
        value=body.get(name,False)
        if type(value) is not bool:
            raise HTTPException(422,'invalid_input')
        result[name]=value
    return result


def _attachment(payload,filename):
    return JSONResponse(payload,headers={'Content-Disposition':f'attachment; filename="{filename}"'})


def _install_nte(bundle,app):
    router=APIRouter(prefix=PREFIX+'/nte/gacha')
    owner=bundle.scope_for('nte','tajiduo')

    @router.get('/summary')
    async def summary(scope=Depends(owner)):
        return bundle.ledger(scope,'nte').summary(scope)

    @router.get('/records')
    async def records(pool_id:str|None=None,limit:int=Query(100,ge=1,le=1000),
                      offset:int=Query(0,ge=0,le=2**31),scope=Depends(owner)):
        return bundle.ledger(scope,'nte').records(scope,pool_id,limit,offset)

    @router.get('/export')
    async def export(pool_id:str|None=None,offset:int|None=Query(None,ge=0,le=2**31),
                     limit:int|None=Query(None,ge=1,le=50000),scope=Depends(owner)):
        return _attachment(bundle.ledger(scope,'nte').export(scope,pool_id,offset=offset,limit=limit),'nte-gacha.json')

    @router.get('/rules')
    async def rules(scope=Depends(owner)):
        return bundle.ledger(scope,'nte').rules(scope)

    @router.post('/preview')
    async def preview(request:Request,scope=Depends(owner)):
        version=bundle.accounts.describe(scope)['version']
        body=await _body(request)
        if bundle.accounts.describe(scope)['version']!=version:
            raise HTTPException(409,'authorization_changed')
        return bundle.ledger(scope,'nte').preview(scope,body.get('document'),**_options(body))

    @router.post('/import')
    async def import_document(request:Request,scope=Depends(owner)):
        version=bundle.accounts.describe(scope)['version']
        body=await _body(request)
        if bundle.accounts.describe(scope)['version']!=version:
            raise HTTPException(409,'authorization_changed')
        return bundle.ledger(scope,'nte').import_document(scope,body.get('document'),
            preview_id=body.get('preview_id'),**_options(body))

    @router.post('/rules')
    async def set_rule(request:Request,scope=Depends(owner)):
        version=bundle.accounts.describe(scope)['version']
        body=await _body(request)
        if bundle.accounts.describe(scope)['version']!=version:
            raise HTTPException(409,'authorization_changed')
        return bundle.ledger(scope,'nte').set_rule(scope,body)

    bundle.include(app,router)


def _install_endfield_gacha(bundle,app):
    router=APIRouter(prefix=PREFIX+'/endfield/gacha')
    owner=bundle.scope_for('endfield','hypergryph')

    @router.get('/summary')
    async def summary(scope=Depends(owner)):
        return bundle.ledger(scope,'endfield_gacha').summary(scope).model_dump(mode='json')

    @router.get('/records')
    async def records(pool_key:str|None=None,limit:int=Query(100,ge=1,le=1000),
                      offset:int=Query(0,ge=0,le=2**31),scope=Depends(owner)):
        return bundle.ledger(scope,'endfield_gacha').records(scope,pool_key,limit,offset)

    @router.get('/export')
    async def export(scope=Depends(owner)):
        return _attachment(bundle.ledger(scope,'endfield_gacha').export(scope),'endfield-gacha.json')

    bundle.include(app,router)


def _install_blueprints(bundle,app):
    router=APIRouter(prefix=PREFIX+'/endfield/blueprints')
    owner=bundle.scope_for('endfield')

    @router.get('')
    async def collection(scope=Depends(owner)):
        return {'items':bundle.ledger(scope,'blueprints').items(scope)}

    @router.get('/export')
    async def export(scope=Depends(owner)):
        return _attachment({'format':'game-assistant-endfield-blueprints','version':1,
            'items':bundle.ledger(scope,'blueprints').items(scope)},'endfield-blueprints.json')

    @router.post('',status_code=201)
    async def create(body:BlueprintInput,scope=Depends(owner)):
        return bundle.ledger(scope,'blueprints').save(scope,body)

    @router.put('/{identity}')
    async def update(identity:str,body:BlueprintInput,scope=Depends(owner)):
        try:
            return bundle.ledger(scope,'blueprints').save(scope,body,identity)
        except KeyError:
            raise HTTPException(404,'private_item_not_found') from None

    @router.delete('/{identity}')
    async def remove(identity:str,scope=Depends(owner)):
        if not bundle.ledger(scope,'blueprints').delete(scope,identity):
            raise HTTPException(404,'private_item_not_found')
        return {'deleted':True}

    bundle.include(app,router)


def _install_wuwa_archive(bundle,app):
    router=APIRouter(prefix=PREFIX+'/wuwa')
    owner=bundle.scope_for('wuthering_waves','kuro')

    @router.get('/history')
    async def history(kind:Literal['tower','roles','role_detail'],limit:int=Query(100,ge=1,le=500),
                      offset:int=Query(0,ge=0,le=1000000),scope=Depends(owner)):
        return bundle.ledger(scope,'wuwa_history').read(scope,kind,limit,offset)

    @router.get('/gacha')
    async def gacha(limit:int=Query(100,ge=1,le=500),offset:int=Query(0,ge=0,le=1000000),scope=Depends(owner)):
        return bundle.ledger(scope,'wuwa_gacha').read(scope,limit,offset)

    @router.post('/history/backfill')
    async def backfill(request:Request,scope=Depends(owner)):
        version=bundle.accounts.describe(scope)['version']
        if await _body(request,1024):
            raise HTTPException(422,'invalid_input')
        if bundle.accounts.describe(scope)['version']!=version:
            raise HTTPException(409,'authorization_changed')
        if bundle.snapshots is None:
            raise HTTPException(503,'scoped_snapshots_unavailable')
        ledger=bundle.ledger(scope,'wuwa_history')
        inserted=0
        for capability in ('combat','roles'):
            snapshot=bundle.snapshots.get_scoped(scope,capability,grant_version=version)
            if snapshot:
                try:
                    inserted+=ledger.capture(scope,capability,json.loads(snapshot['payload']),
                        observed_at=snapshot['fetched_at'])
                except (ValueError,TypeError):
                    continue
        return {'inserted':inserted,'complete':False,'sources':['scoped_snapshot'],
            'message':'仅回补现存同账号快照；官方无已验证的历史成绩接口，未推测旧记录'}

    @router.post('/gacha/import')
    async def import_gacha(request:Request,scope=Depends(owner)):
        info=bundle.accounts.describe(scope)
        value=await _body(request,2*1024*1024)
        if bundle.accounts.describe(scope)['version']!=info['version']:
            raise HTTPException(409,'authorization_changed')
        if set(value) not in ({'url'},{'records'}):
            raise HTTPException(422,'invalid_input')
        failed=[];source='json_import'
        try:
            if 'url' in value:
                result=await fetch_official(value['url'],info['game_uid'],info['server'])
                if bundle.accounts.describe(scope)['version']!=info['version']:
                    raise HTTPException(409,'authorization_changed')
                records,failed,source=result['records'],result['failed_pools'],'official_query'
            else:
                records=value['records']
            return bundle.ledger(scope,'wuwa_gacha').import_records(scope,records,source=source,failed_pools=failed)
        except ValueError:
            raise HTTPException(422,'invalid_gacha_input') from None

    bundle.include(app,router)


def _install_wuwa_details(bundle,app):
    router=APIRouter(prefix=PREFIX+'/wuwa')
    owner=bundle.scope_for('wuthering_waves','kuro')

    async def read(scope,capability,method,*args):
        info=bundle.accounts.describe(scope)
        registry=bundle.runtime.for_scope(scope)
        adapter=registry.get('wuthering_waves')
        result=await adapter._auth.fetch('wuthering_waves',capability,lambda:getattr(adapter,method)(*args))
        if bundle.accounts.describe(scope)['version']!=info['version'] or result.credential_version!=info['version']:
            raise HTTPException(409,'authorization_changed')
        if not result.ok:
            raise HTTPException({'not_found':404,'unconfigured':401,'auth_expired':401,'account_changed':409}.get(result.error_kind,502),
                                'private_query_failed')
        payload=jsonable_encoder(result.payload)
        if method=='fetch_role_detail':
            bundle.ledger(scope,'wuwa_history').capture(scope,'role_detail',payload)
        from datetime import datetime,timezone
        return {'payload':payload,'fetched_at':datetime.now(timezone.utc).isoformat()}

    @router.get('/roles/{character_id}')
    async def role_detail(character_id:str,scope=Depends(owner)):
        if not character_id.isdigit() or not 1<=len(character_id)<=12:
            raise HTTPException(422,'invalid_input')
        return await read(scope,Capability.ROLES,'fetch_role_detail',character_id)

    @router.get('/resources/{kind}/{period}')
    async def resources(kind:Literal['week','month','version'],period:str,scope=Depends(owner)):
        if len(period)>64 or not period or not all(c.isascii() and (c.isalnum() or c in '_.-') for c in period):
            raise HTTPException(422,'invalid_input')
        return await read(scope,Capability.RESOURCES,'fetch_resource_detail',kind,period)

    bundle.include(app,router)


def _install_skland(bundle,app):
    router=APIRouter(prefix=PREFIX+'/endfield/skland')
    owner=bundle.scope_for('endfield','skland')

    async def read(scope,method,*args,**kwargs):
        version=bundle.accounts.describe(scope)['version']
        try:
            result=await getattr(bundle.skland(scope),method)(scope,*args,**kwargs)
        except SklandError:
            raise HTTPException(502,'skland_query_failed') from None
        if bundle.accounts.describe(scope)['version']!=version:
            raise HTTPException(409,'authorization_changed')
        return result

    @router.get('/card')
    async def card(scope=Depends(owner)):
        return await read(scope,'read_card')

    @router.get('/attendance')
    async def attendance(scope=Depends(owner)):
        return await read(scope,'attendance_status')

    @router.get('/operators/{char_id}')
    async def operator(char_id:str,scope=Depends(owner)):
        return await read(scope,'read_operator',char_id)

    @router.get('/challenges')
    async def challenges(kind:str,season_id:str|None=None,contract_id:str|None=None,record_id:str|None=None,scope=Depends(owner)):
        return await read(scope,'read_challenges',kind,season_id=season_id,contract_id=contract_id,record_id=record_id)

    @router.get('/tools')
    async def tools(kind:str,char_id:str|None=None,scope=Depends(owner)):
        return await read(scope,'read_tool',kind,char_id=char_id)

    bundle.include(app,router)


def install_cloud_private_routes(app,accounts,runtime,private_root,*,snapshots=None):
    """Create only reviewed scoped endpoints. Root explicitly calls allowlist()."""
    if not hasattr(app.state,'cloud_route_policy'):
        raise ValueError('Cloud route boundary must be configured first')
    bundle=PrivateRoutes(accounts,runtime,private_root,snapshots)

    @app.exception_handler(AccountNotFoundError)
    async def missing(request,error):
        return JSONResponse({'error_code':'account_not_found','detail':'账号或角色不存在'},status_code=404)

    @app.exception_handler(GachaError)
    async def ledger_error(request,error):
        return JSONResponse({'error_code':'invalid_gacha_input','detail':str(error)},status_code=error.status)

    from .nte_gacha_routes import install_cloud_nte_gacha_routes
    from .endfield_gacha_routes import install_cloud_endfield_gacha_routes
    from .endfield_blueprint_routes import install_cloud_endfield_blueprint_routes
    from .wuwa_archive_routes import install_cloud_wuwa_archive_routes
    from .adapters.wuthering_waves.routes import install_cloud_wuwa_routes
    from .endfield_skland_routes import install_cloud_endfield_skland_routes
    for install in (install_cloud_nte_gacha_routes,install_cloud_endfield_gacha_routes,
                    install_cloud_endfield_blueprint_routes,install_cloud_wuwa_archive_routes,
                    install_cloud_wuwa_routes,install_cloud_endfield_skland_routes):
        install(app,bundle)
    return bundle


# Exact route/method declarations: prefixes never implicitly approve new routes.
LOCAL_ROUTE_POLICY = {}


def _declare(category, method, *paths, policy='disabled_legacy'):
    for path in paths:
        LOCAL_ROUTE_POLICY[(method,path)] = (category,policy)


_declare('disabled','GET','/openapi.json','/docs','/docs/oauth2-redirect','/redoc',policy='disabled')
_declare('disabled','HEAD','/openapi.json','/docs','/docs/oauth2-redirect','/redoc',policy='disabled')
_declare('private_query','GET',
    '/api/auth/status','/api/nte/gacha/summary','/api/nte/gacha/records','/api/nte/gacha/export','/api/nte/gacha/rules',
    '/api/endfield/gacha/summary','/api/endfield/gacha/records','/api/endfield/gacha/export',
    '/api/endfield/blueprints','/api/endfield/blueprints/export','/api/endfield/skland/status',
    '/api/endfield/skland/card','/api/endfield/skland/attendance','/api/endfield/skland/operators/{char_id}',
    '/api/endfield/skland/challenges','/api/endfield/skland/tools','/api/wuwa/roles/{role_id}',
    '/api/wuwa/resources/{kind}/{period}','/api/wuwa/history','/api/wuwa/gacha',
    '/api/games/{game_id}/snapshot/{capability}','/api/status','/api/games/{game_id}/match/{match_id}/detail')
_declare('private_modify','POST',
    '/api/auth/{game}/sessions','/api/auth/{game}/sms','/api/auth/{game}/login',
    '/api/nte/gacha/preview','/api/nte/gacha/import','/api/nte/gacha/rules','/api/endfield/blueprints',
    '/api/endfield/skland/connect','/api/endfield/skland/role','/api/endfield/skland/refresh',
    '/api/wuwa/history/backfill','/api/wuwa/gacha/import','/api/games/{game_id}/refresh')
_declare('private_modify','PUT','/api/endfield/blueprints/{identity}')
_declare('private_modify','DELETE','/api/auth/{game}','/api/endfield/blueprints/{identity}','/api/endfield/skland/connection')
_declare('public_read_only','GET','/api/endfield/public','/api/endfield/map','/api/endfield/map/marks/{mark_id}',
    '/api/nte/guides','/api/nte/guides/sources/{post_id}','/api/wuwa/guides/updates','/api/health','/api/games',
    policy='reviewed_read_only')
_declare('admin_sources','POST','/api/endfield/public/refresh','/api/nte/guides/sources/{post_id}/refresh',
    '/api/wuwa/guides/updates','/api/wuwa/guides/updates/extract','/api/lol/esports/refresh',
    '/api/auth/bilibili-source/credentials','/api/sources/bilibili/{game}/refresh',policy='admin_required')
_declare('admin_sources','GET','/api/auth/bilibili-source/login/status',
    '/api/auth/bilibili-source/login/sessions/{sid}','/api/sources/bilibili','/api/sources/bilibili/{game}/audit',policy='admin_required')
_declare('admin_sources','POST','/api/auth/bilibili-source/login/sessions',
    '/api/auth/bilibili-source/login/sessions/{sid}/captcha','/api/auth/bilibili-source/login/sessions/{sid}/password',
    '/api/auth/bilibili-source/login/sessions/{sid}/sms/send','/api/auth/bilibili-source/login/sessions/{sid}/sms/submit',
    '/api/auth/bilibili-source/login/sessions/{sid}/qr/poll','/api/auth/bilibili-source/login/sessions/{sid}/cookie',
    '/api/auth/bilibili-source/login/sessions/{sid}/commit',policy='admin_required')
_declare('admin_sources','DELETE','/api/auth/bilibili-source/login/sessions/{sid}',policy='admin_required')
_declare('disabled','POST','/api/endfield/skland/attendance','/api/lol/collect',policy='disabled')
_declare('disabled','GET','/api/lol/analysis','/api/lol/matches/{match_id}',policy='disabled')
for _method in ('GET','HEAD','POST','PUT','PATCH','DELETE','OPTIONS','TRACE','CONNECT'):
    _declare('disabled',_method,'/{path:path}',policy='disabled_local_spa')


def iter_routes(routes):
    """Support FastAPI flattened routes and lazy IncludedRouter containers."""
    for route in routes:
        original=getattr(route,'original_router',None)
        if original is not None:
            yield from iter_routes(original.routes)
        elif hasattr(route,'path'):
            yield route
        else:
            raise ValueError('Unclassified route container')


def local_route_inventory(app):
    """Classify every installed local route; this never grants cloud access."""
    inventory=[]
    for route in iter_routes(app.routes):
        methods=getattr(route,'methods',None)
        if methods is None:
            raise ValueError('Unclassified route mount: '+route.path)
        for method in sorted(methods):
            key=(method,route.path)
            if key not in LOCAL_ROUTE_POLICY:
                raise ValueError('Unclassified local route: '+method+' '+route.path)
            category,policy=LOCAL_ROUTE_POLICY[key]
            inventory.append(dict(method=method,path=route.path,category=category,cloud_policy=policy))
    return sorted(inventory,key=lambda item:(item['path'],item['method']))
