"""Synthetic-only HTTPS website QA. No upstream collector or production config."""
import argparse
from contextlib import asynccontextmanager, closing
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys

try:
    from .backup import OperationError, safe_path
except ImportError:
    from backup import OperationError, safe_path

SYNTHETIC_PASSWORD = 'Synthetic-test-password-01'
GAMES = {'kuro':'wuthering_waves','tajiduo':'nte','hypergryph':'endfield'}


def provision(destination, frontend_dist=None, users=2, port=8443):
    destination = safe_path(destination)
    if destination.exists() or not 2 <= users <= 20 or not 1024 <= port <= 65535:
        raise OperationError('new_synthetic_directory_required')
    from game_assistant.cloud_web_ui import validate_dist
    if frontend_dist:
        frontend_dist = validate_dist(frontend_dist)
    destination.mkdir(parents=True, mode=0o700)
    root = destination / 'data'
    root.mkdir()
    key = destination / 'synthetic-grants.key'
    with os.fdopen(os.open(key, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600),'wb') as stream:
        stream.write(os.urandom(32))
    # No real user/database discovery: every value here is manufactured.
    from game_assistant.config import Settings
    from game_assistant.identity.store import IdentityStore
    from game_assistant.identity.service import IdentityService
    from game_assistant.identity.models import Principal
    from game_assistant.auth.store import CredentialStore
    from game_assistant.accounts.service import AccountService
    from game_assistant.snapshots import SnapshotStore
    settings = Settings(cloud_db_path=str(root/'identity.db'))
    identity = IdentityService(IdentityStore(settings.cloud_db_path), settings)
    hashed = identity.hasher.hash(SYNTHETIC_PASSWORD)
    with identity.store.connect(write=True) as db:
        for number in range(1,users+1):
            db.execute('INSERT INTO users(user_id,username,password_hash,is_admin) VALUES(?,?,?,?)',
                (f'synthetic-{number:02}',f'qa_user_{number:02}',hashed,int(number==1)))
    with closing(sqlite3.connect(root/'identity.db')) as db:
        db.execute('PRAGMA foreign_keys=ON')
        accounts = AccountService(db, CredentialStore('unused',connection=db,key_path=key))
        snapshots = SnapshotStore(str(root/'snapshots.db'))
        try:
            for number in range(1,users+1):
                principal = Principal(f'synthetic-{number:02}',number==1)
                for provider,game in GAMES.items():
                    credentials = {'user_id':f'synthetic-{number:02}', 'center_uid':f'synthetic-{number:02}',
                        'uid':f'synthetic-{number:02}', 'role_id':f'fixture-{provider}-{number:02}',
                        'server_id':'official','access_token':'SYNTHETIC-NOT-A-TOKEN',
                        'token':'SYNTHETIC-NOT-A-TOKEN','nickname':f'合成用户 {number:02}'}
                    row = accounts.save_verified(principal,provider,credentials)
                    scope = accounts.require_scope(principal,row['account_id'],row['role_id'])
                    values = {'account':{'nickname':f'合成用户 {number:02}', 'name':f'合成用户 {number:02}',
                        'level':40+number,'uid':f'SYNTHETIC-{number:02}', 'synthetic_owner':principal.user_id},
                        'stamina':{'current':80+number,'max':240,'recovery_seconds':None},
                        'gacha':{'total_count':None,'history_complete':False,'records':[]}}
                    for capability,payload in values.items():
                        snapshots.save_scoped(scope,capability,json.dumps(payload,ensure_ascii=False),row['version'])
                        from game_assistant.models import FetchResult
                        snapshots.record_poll_scoped(scope,capability,FetchResult(ok=True,payload=payload),row['version'])
            for game in GAMES.values():
                snapshots.save(game,'news',json.dumps([{'id':'synthetic-news','title':'合成验收资讯',
                    'url':'https://example.invalid/synthetic','source':'合成夹具','synthetic':True}]))
                snapshots.save(game,'events',json.dumps([{'id':'synthetic-event','name':'合成验收活动',
                    'start':None,'end':None,'source':'合成夹具','synthetic':True}]))
                for capability in ('news','events'):
                    snapshots.record_poll(game,capability,FetchResult(ok=True))
        finally:
            snapshots._conn.close()
    config = {'cloud_accounts_enabled':True,'cloud_db_path':str(root/'identity.db'),
        'cloud_data_root':str(root),'cloud_credentials_key_path':str(key),
        'cloud_allowed_origins':[f'https://localhost:{port}'],
        'wuwa_enabled':False,'nte_enabled':False,'endfield_enabled':False}
    lines = [f'{name}={json.dumps(value,ensure_ascii=False).lower() if isinstance(value,bool) else json.dumps(value,ensure_ascii=False)}'
             for name,value in config.items()]
    lines.extend(['[runtime]','host="127.0.0.1"',f'port={port}'])
    if frontend_dist:
        lines.append('frontend_dist=' + json.dumps(str(frontend_dist),ensure_ascii=False))
    (destination/'cloud.toml').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (destination/'synthetic-only.json').write_text(json.dumps({'format':1,'synthetic':True,'users':users,
        'credentials':'all synthetic; never paste real tokens','upstream_disabled':True})+'\n')
    certificate(destination)
    return {'status':'synthetic_fixture_ready','users':users,'origin':f'https://localhost:{port}',
        'username':'qa_user_01','password':SYNTHETIC_PASSWORD,'upstream':'disabled'}


def certificate(destination):
    # Existing QQ extra includes cryptography. QA cert is never a production cert.
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    from ipaddress import ip_address
    key = rsa.generate_private_key(public_exponent=65537,key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'localhost synthetic QA only')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1))
        .not_valid_after(now+timedelta(days=7))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost'),
            x509.IPAddress(ip_address('127.0.0.1'))]),critical=False).sign(key,hashes.SHA256()))
    (destination/'localhost.crt').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    path = destination/'localhost.key'
    with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as stream:
        stream.write(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,
                                     serialization.NoEncryption()))


def qa_app(destination):
    destination = safe_path(destination)
    marker = json.loads((destination/'synthetic-only.json').read_text())
    if marker.get('synthetic') is not True or marker.get('upstream_disabled') is not True:
        raise OperationError('synthetic_fixture_required')
    from game_assistant.cloud_runtime import load_runtime,build_app
    runtime = load_runtime(destination/'cloud.toml')
    if Path(runtime.settings.cloud_data_root) != destination/'data' or Path(runtime.settings.cloud_db_path) != destination/'data/identity.db':
        raise OperationError('synthetic_path_mismatch')
    with closing(sqlite3.connect(runtime.settings.cloud_db_path)) as db:
        rows = db.execute('SELECT user_id,username FROM users').fetchall()
        if len(rows) != marker['users'] or any(not owner.startswith('synthetic-') or not username.startswith('qa_user_') for owner,username in rows):
            raise OperationError('synthetic_users_required')
    app = build_app(runtime,start_scheduler=False)
    original = app.router.lifespan_context
    @asynccontextmanager
    async def synthetic_lifespan(owner):
        async with original(owner):
            from game_assistant.registry import GameRegistry
            from game_assistant.models import Capability,FetchResult
            class SyntheticAdapter:
                capabilities = [Capability.ACCOUNT,Capability.STAMINA,Capability.GACHA]
                def __init__(self,game,scope,version):
                    self.game_id = game
                    self.scope,self.version = scope,version
                    self.display_name = {'wuthering_waves':'鸣潮','nte':'异环','endfield':'终末地'}[game]
                def prepare_refresh(self): pass
                async def fetch(self,capability):
                    import asyncio
                    await asyncio.sleep(0.025)
                    cached = app.state.store.get_scoped(self.scope,capability.value,grant_version=self.version)
                    return FetchResult(ok=True,payload=json.loads(cached['payload']) if cached else None)
            def registry(scope):
                info = app.state.accounts.describe(scope)
                result = GameRegistry()
                result.register(SyntheticAdapter(info['game'],scope,info['version']))
                return result
            app.state.account_runtime.for_scope = registry
            app.state.public_query.sources = list(GAMES.values())
            # Manual jobs exercise genuine queue/coalescing against synthetic
            # cached adapters. No periodic jobs and no upstream HTTP clients.
            app.state.scheduler.start(periodic=False)
            yield
    app.router.lifespan_context = synthetic_lifespan
    from starlette.responses import JSONResponse
    class NoUpstream:
        def __init__(self, app): self.app=app
        async def __call__(self,scope,receive,send):
            if scope['type']=='http' and (scope['path'].startswith('/api/accounts/auth/')
                    or scope['path'].startswith('/internal/qq/')):
                return await JSONResponse({'detail':'synthetic_upstream_disabled'},status_code=503)(scope,receive,send)
            await self.app(scope,receive,send)
    app.add_middleware(NoUpstream)
    return app,runtime


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['create','serve'])
    parser.add_argument('--destination',required=True,help='Explicit new ignored synthetic directory')
    parser.add_argument('--frontend-dist',help='Cloud build marked by build_frontend.py')
    parser.add_argument('--users',type=int,default=2)
    parser.add_argument('--port',type=int,default=8443)
    args=parser.parse_args(argv)
    try:
        if args.action=='create':
            print(json.dumps(provision(args.destination,args.frontend_dist,args.users,args.port)))
        else:
            app,runtime=qa_app(args.destination)
            import uvicorn
            uvicorn.run(app,host='127.0.0.1',port=runtime.port,workers=1,proxy_headers=False,
                access_log=False,ssl_certfile=str(Path(args.destination)/'localhost.crt'),
                ssl_keyfile=str(Path(args.destination)/'localhost.key'),limit_concurrency=64)
        return 0
    except (OperationError,ValueError,OSError,ImportError) as error:
        # Fixture-only errors carry no user payload; stable code plus class is
        # sufficient to diagnose setup without exposing arbitrary exception text.
        code=str(error) if isinstance(error,OperationError) else type(error).__name__
        print('synthetic_qa_failed: '+code,file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
