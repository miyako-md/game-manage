"""Local and authenticated cloud preference configuration/assessment routes."""
import json
from pathlib import Path
from typing import Literal, Annotated
from fastapi import APIRouter, Depends, HTTPException, Request, Path as ApiPath
from pydantic import ValidationError
from .assessment import AssessmentModel, Configuration, assess, compare
from .assessment_store import AssessmentStore
from .assessment_defaults import resolve_model
from .assessment_equipped import equipped_configuration
from .assessment_nte_math import validate_profile
from .accounts.models import AccountScope
from .identity.dependencies import require_user
from .wuwa_role_detail import archived_role_detail

Character = Annotated[str, ApiPath(min_length=1,max_length=256)]


def install_assessment_routes(app,accounts=None,private_root=None,snapshots=None):
    cloud=accounts is not None
    root=Path(private_root) if cloud else Path(app.state.settings.db_path).parent
    store=AssessmentStore(root/'personal-assessments.db')
    app.state.assessments=store
    prefix='/api/accounts/{account_id}/roles/{role_id}/assessment' if cloud else '/api/assessment'
    router=APIRouter(prefix=prefix)

    async def owner(request:Request,game:Literal['nte','wuthering_waves'],principal=Depends(require_user) if cloud else None):
        if cloud:
            scope=accounts.require_scope(principal,request.path_params['account_id'],request.path_params['role_id'])
            info=accounts.describe(scope)
            if info['game']!=game: raise HTTPException(404,'account_not_found')
            return scope,info['version']
        try: adapter=app.state.registry.get(game)
        except KeyError: raise HTTPException(404,'game_not_available') from None
        if not adapter.credentials_configured: raise HTTPException(401,'account_required')
        settings=adapter._settings
        uid=str(settings.nte_role_id if game=='nte' else settings.wuwa_role_id)
        server='official' if game=='nte' else str(settings.wuwa_server_id)
        if not uid or not server: raise HTTPException(401,'account_required')
        return AccountScope('local',game+':'+server,uid),app.state.auth.account_generation(game)

    async def read_body(request,authorization,game):
        raw=bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw)>128*1024: raise HTTPException(413,'input_too_large')
        try: body=json.loads(raw)
        except (ValueError,UnicodeError,RecursionError): raise HTTPException(422,'invalid_input') from None
        if not isinstance(body,dict): raise HTTPException(422,'invalid_input')
        scope,version=authorization
        if cloud:
            if accounts.describe(scope)['version']!=version: raise HTTPException(409,'authorization_changed')
        elif app.state.auth.account_generation(game)!=version: raise HTTPException(409,'authorization_changed')
        return body

    def selected(scope,game,character): return resolve_model(store,scope,game,character)[0]

    def configuration(scope,game,character,identity):
        row=next((r for r in store.read(scope,game,character,'configuration') if r['id']==identity),None)
        if not row: raise HTTPException(404,'configuration_not_found')
        # A row stored before a contract was tightened stays listed and deletable but cannot be scored.
        try: return Configuration.model_validate(row['data'])
        except ValidationError: raise HTTPException(422,'invalid_scoring_input') from None

    def validate(cls,body,game,character):
        # A saved copy of a default is the user's own model and carries no attribution.
        if cls is AssessmentModel and body.get('source')=='user_configured': body={k:v for k,v in body.items() if k!='attribution'}
        try:
            result=cls.model_validate(body)
            if (result.game,result.character_id)!=(game,character): raise ValueError('identity mismatch')
            # Only users configure: a body claiming the built-in default is refused, not stored.
            if result.source!='user_configured': raise ValueError('source must be user configured')
            return result
        except (ValueError,ValidationError): raise HTTPException(422,'invalid_input') from None

    @router.get('/{game}/{character}')
    async def read(game:Literal['nte','wuthering_waves'],character:Character,authorization=Depends(owner)):
        scope,_=authorization
        return dict(model=selected(scope,game,character).model_dump(mode='json'),configurations=store.read(scope,game,character,'configuration'))

    @router.put('/{game}/{character}/model')
    async def model(request:Request,game:Literal['nte','wuthering_waves'],character:Character,authorization=Depends(owner)):
        value=validate(AssessmentModel,await read_body(request,authorization,game),game,character)
        # A weight on a catalog row that cannot take it would make every later score unscorable.
        if value.nte_profile is not None and value.nte_spec is not None:
            try: validate_profile(value.nte_profile,value.nte_spec)
            except ValueError: raise HTTPException(422,'invalid_input') from None
        return store.save(authorization[0],value,'model')

    @router.delete('/{game}/{character}/model')
    async def restore(game:Literal['nte','wuthering_waves'],character:Character,authorization=Depends(owner)):
        # Restores the built-in default (or none): the saved model wholly replaced it.
        return dict(deleted=store.delete(authorization[0],game,character,'selected',kind='model'))

    @router.post('/{game}/{character}/configurations',status_code=201)
    async def save(request:Request,game:Literal['nte','wuthering_waves'],character:Character,authorization=Depends(owner)):
        value=validate(Configuration,await read_body(request,authorization,game),game,character)
        try: return store.save(authorization[0],value,'configuration')
        except ValueError: raise HTTPException(422,'configuration_limit') from None

    @router.delete('/{game}/{character}/configurations/{identity}')
    async def remove(game:Literal['nte','wuthering_waves'],character:Character,identity:str,authorization=Depends(owner)):
        if not store.delete(authorization[0],game,character,identity): raise HTTPException(404,'configuration_not_found')
        return dict(deleted=True)

    @router.post('/{game}/{character}/score')
    async def score(request:Request,game:Literal['nte','wuthering_waves'],character:Character,authorization=Depends(owner)):
        body=await read_body(request,authorization,game); scope=authorization[0]
        value=configuration(scope,game,character,body['id']) if isinstance(body.get('id'),str) else validate(Configuration,body.get('configuration'),game,character)
        try: return assess(value,selected(scope,game,character))
        except ValueError: raise HTTPException(422,'invalid_scoring_input') from None

    @router.post('/{game}/{character}/compare')
    async def comparison(request:Request,game:Literal['nte','wuthering_waves'],character:Character,authorization=Depends(owner)):
        body=await read_body(request,authorization,game); scope=authorization[0]
        if set(body)!= {'a','b'} or not all(isinstance(body[k],str) for k in body): raise HTTPException(422,'invalid_input')
        a,b=configuration(scope,game,character,body['a']),configuration(scope,game,character,body['b'])
        try: return compare(a,b,selected(scope,game,character))
        except ValueError: raise HTTPException(422,'invalid_scoring_input') from None

    @router.get('/{game}/{character}/equipped')
    async def equipped(game:Literal['nte','wuthering_waves'],character:Character,authorization=Depends(owner)):
        scope,version=authorization; payload={}; observed=None
        if game=='nte':
            if cloud and snapshots: version,generation=accounts.snapshot_bounds(scope)
            snap=snapshots.get_scoped(scope,'roles',grant_version=version,
                minimum_version=generation) if cloud and snapshots else app.state.store.get(game,'roles') if not cloud else None
            if snap: payload=json.loads(snap['payload']); observed=snap['fetched_at']
        elif cloud:
            from .wuwa_history import WuwaHistory
            from .private_data import scope_directory
            info=accounts.describe(scope)
            rows=[]
            if (scope_directory(root,scope)/'wuwa_history'/'ledger.sqlite3').is_file():
                archive=WuwaHistory.for_scope(scope,root,role_uid=info['game_uid'],server_id=info['server'])
                try: rows=archive.read(scope,'role_detail',limit=20,subject=character)['items']
                finally: archive.close()
            retained,observed=archived_role_detail(rows,character)
            if retained is not None:payload=retained
        else:
            settings=app.state.registry.get(game)._settings
            rows=app.state.store.wuwa_history.read(str(settings.wuwa_role_id),str(settings.wuwa_server_id),'role_detail',20,subject=character)['items']
            retained,observed=archived_role_detail(rows,character)
            if retained is not None:payload=retained
        value=equipped_configuration(game,character,payload,observed)
        return dict(configuration=value.model_dump(mode='json'),assessment=assess(value,selected(scope,game,character)))

    app.include_router(router)
    if cloud:
        from .cloud_app import allow_cloud_route
        for route in router.routes: allow_cloud_route(app,route.path,route.methods)
    return store
