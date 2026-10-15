"""QQ service-only cached queries; no login or upstream I/O on messages."""
from typing import Literal
import base64
import hashlib
import json
import time
from datetime import datetime

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from game_assistant.accounts.store import AccountNotFoundError
from game_assistant.auth.store import CredentialStoreError
from game_assistant.accounts.models import AccountScope, QueryResult
from .bindings import QqBindingError
from .commands import GAME_NAMES, PAGED_COMMANDS, MAX_PAGE, safe_text
from .internal_routes import IdentityBody
from .rendering import RenderQueue, SummaryRenderer
from .cards import card_to_text
from . import presentation as view


class QueryBody(BaseModel):
    model_config=ConfigDict(extra='forbid')
    identity: IdentityBody
    command: Literal['help','status','overview','summary','roles','stamina','exploration','combat','progress','gacha',
                     'calendar','events','recent_events','news','refresh','dashboard','calabash','activities','resources','realestate','vehicles','teams','record']
    game: Literal['wuthering_waves','nte','endfield'] | None = None
    image_requested: bool = False
    render_budget_seconds: float = Field(default=0, ge=0, le=10, allow_inf_nan=False)
    role_name: str | None = Field(default=None, min_length=1, max_length=64)
    page: int = Field(default=1, ge=1, le=MAX_PAGE, strict=True)

    @model_validator(mode='after')
    def selectors_only(self):
        if self.role_name is not None and (self.command!='roles' or self.game is None or not self.role_name.isprintable()):
            raise ValueError('named_role_only')
        if self.page!=1 and self.command not in PAGED_COMMANDS:
            raise ValueError('page_not_supported')
        if self.command=='overview' and self.game is not None:
            raise ValueError('overview_all_games')
        return self


class QqQueryService:
    def __init__(self, bindings, query, public, *, dashboard_url='', urls_approved=False, render_queue=None,asset_cache=None,clock=None,private_poll_seconds=300):
        self.bindings,self.query_service,self.public=bindings,query,public
        self.dashboard_url,self.urls_approved=dashboard_url,urls_approved
        self.render_queue=render_queue
        self.asset_cache=asset_cache
        self.clock=clock or (lambda:datetime.now(view.BEIJING))
        self.private_poll_seconds=private_poll_seconds
        if render_queue is not None and query is not None:
            query.accounts._listeners.append(self.invalidate)

    def invalidate(self, user_id, grant_id):
        self.render_queue.renderer.invalidate_account(user_id)

    async def aclose(self):
        if self.render_queue is not None:
            await self.render_queue.aclose()
            if self.query_service is not None and self.invalidate in self.query_service.accounts._listeners:
                self.query_service.accounts._listeners.remove(self.invalidate)
        if self.asset_cache is not None:await self.asset_cache.aclose()

    def _accounts(self,principal,game,*,command=None,account_rows=None):
        rows=[r for r in (account_rows if account_rows is not None else self.query_service.list_accounts(principal))
              if r['game']==game and r['state']=='active' and r['roles']]
        if game=='endfield' and command=='gacha':
            rows=[r for r in rows if r['provider']=='hypergryph']
        elif game=='endfield' and any(r['provider']=='skland' for r in rows):
            rows=[r for r in rows if r['provider']=='skland']
        if not rows:return []
        # Match CloudApp's first available account and default-or-first role.
        row=rows[0]
        role=next((r for r in row['roles'] if r['is_default']),row['roles'][0])
        scope=self.query_service.accounts.require_scope(principal,row['account_id'],role['role_id'])
        return [(row,scope)]

    def _binding_revision(self, identity):
        # Confirm the exact active link, including unlink/relink to the same user.
        store=getattr(self.bindings,'store',None)
        if store is None:return None
        with store.connect() as db:
            row=db.execute('SELECT link_id FROM qq_links WHERE app_id=? AND scene=? AND group_openid IS ? '
                           'AND sender_openid=? AND revoked_at IS NULL',
                           (identity.app_id,identity.scene,identity.group_openid,identity.sender_openid)).fetchone()
        return row['link_id'] if row else None

    def _capture_scope(self, context, scope):
        if context is None:return
        if any(previous==scope for previous,_ in context['grants']):return
        context['grants'].append((scope,self.query_service.accounts.describe(scope)['version']))

    def _capture_snapshot(self, context, scope, cap, snapshot):
        if context is None:return
        identity=(scope.user_id,scope.account_id,scope.role_id) if scope else ('public',)
        encoded=json.dumps([identity,cap,snapshot.payload,snapshot.fetched_at,snapshot.state,snapshot.complete],
                           ensure_ascii=False,sort_keys=True,default=str).encode()
        fingerprint=hashlib.sha256(encoded).hexdigest()
        if fingerprint not in context['fingerprints']:
            context['snapshots'].append(snapshot)
            context['fingerprints'].append(fingerprint)
        if scope is None and ':' in cap:
            from dataclasses import asdict
            game,capability=cap.split(':',1)
            context.setdefault('public_snapshots',{}).setdefault(game,{})[capability]=asdict(snapshot)

    def _reply(self, card, page, context, *, paged=False):
        card=view.long_document(card,page,asset_cache=self.asset_cache)
        if context is not None:context['card']=card
        return {'text':card_to_text(card)}

    def _ledger_snapshot(self, scope, game):
        """Read only an existing scoped shard; missing files never get initialized."""
        private=getattr(self.query_service,'private',None)
        kind={'wuthering_waves':'wuwa_gacha','nte':'nte','endfield':'endfield_gacha'}[game]
        if private is None:return None
        root=getattr(private,'private_root',None)
        if root is not None:
            from game_assistant.private_data import scope_directory
            if not (scope_directory(root,scope)/kind/'ledger.sqlite3').is_file():return None
        ledger=private.ledger(scope,kind)
        payload=ledger.read(scope,500,0) if game=='wuthering_waves' else ledger.summary(scope)
        if hasattr(payload,'model_dump'):payload=payload.model_dump(mode='json')
        data=view.obj(payload)
        coverage=view.obj(data.get('coverage'))
        times=[pool.get('last_sync_at') for pool in view.rows(data.get('pools')) if isinstance(pool.get('last_sync_at'),str)]
        fetched=coverage.get('imported_at') or max(times,default=None)
        complete=data.get('complete') if type(data.get('complete')) is bool else coverage.get('complete')
        return QueryResult(payload,fetched,'ok',complete if type(complete) is bool else None)

    def _role_detail_snapshot(self, scope, character_id, cache=None):
        private=getattr(self.query_service,'private',None)
        if private is None or character_id is None:return None
        root=getattr(private,'private_root',None)
        if root is not None:
            from game_assistant.private_data import scope_directory
            if not (scope_directory(root,scope)/'wuwa_history'/'ledger.sqlite3').is_file():return None
        # Fixed recent-observation window; no upstream lookup or arbitrary SQL.
        key=(scope,'role_detail_history')
        history=cache.get(key) if cache is not None else None
        if history is None:
            history=private.ledger(scope,'wuwa_history').read(scope,'role_detail',100,0)
            if cache is not None:cache[key]=history
        found=next((item for item in view.rows(view.obj(history).get('items'))
                    if str(item.get('subject'))==str(character_id)),None)
        if found is None:return None
        payload=view.obj(found.get('payload'))
        if str(payload.get('character_id'))!=str(character_id):return None
        return QueryResult(view.obj(payload.get('data')),found.get('observed_at') or found.get('source_at') or found.get('archived_at'),
                           'ok',False)

    def _snapshot(self,row,scope,cap,context,cache=None):
        game,provider=row['game'],row['provider']
        caps=self.query_service.capabilities(scope)
        # Skland account snapshots contain observed subviews; no extra fetch.
        embedded=provider=='skland' and cap in ('roles','stamina','exploration','progress') and 'account' in caps
        actual='account' if embedded else cap
        if cap=='gacha' and provider!='skland' and game!='nte':
            ledger=self._ledger_snapshot(scope,game)
            if ledger is not None:
                self._capture_snapshot(context,scope,cap,ledger)
                return ledger
            if cap not in caps and game=='wuthering_waves':
                snapshot=QueryResult({'state':'need_import'},None,'never',False)
                self._capture_snapshot(context,scope,cap,snapshot)
                return snapshot
        if actual not in caps:return None
        key=(scope.account_id,scope.role_id,actual)
        if cache is not None and key in cache:snapshot=cache[key]
        else:
            snapshot=self.query_service.read(scope,actual)
            if cache is not None:cache[key]=snapshot
        self._capture_snapshot(context,scope,actual,snapshot)
        if embedded and cap=='stamina':
            snapshot=QueryResult(view.obj(snapshot.payload).get('stamina'),snapshot.fetched_at,snapshot.state,snapshot.complete)
        return snapshot

    def _public_events(self,games,command,context):
        from .event_views import event_document
        snapshots={}
        for current in games:
            try:
                snapshot=self.public.read(current,'events') if self.public is not None else QueryResult(None,None,'never',None)
            except (AccountNotFoundError,HTTPException,ValueError,RuntimeError,OSError):snapshot=QueryResult(None,None,'error',None)
            snapshots[current]=snapshot
            self._capture_snapshot(context,None,current+':events',snapshot)
        return event_document(command,snapshots,now=self.clock(),asset_cache=self.asset_cache)

    def query(self,identity,command,game=None,*,image_context=None,role_name=None,page=1):
        context=image_context
        read_cache={}
        detail_cache={}
        if context is not None:context.update(grants=[],snapshots=[],fingerprints=[],user_id=None,read_cache=read_cache,detail_cache=detail_cache)
        reply=lambda card, paged=False:self._reply(card,page,context,paged=paged)
        if command=='help':
            card=view.help_document(game)
            return reply(card)
        if command=='dashboard':
            value=self.dashboard_url if self.urls_approved and self.dashboard_url else '看板网址尚未启用；请通过已保存的网站入口查看。'
            return {'text':safe_text(value,urls_approved=self.urls_approved)}
        if command in ('calendar','events','recent_events') and game is not None:
            return reply(self._public_events([game],command,context),True)
        if command=='news':
            if self.public is None or game is None:return reply(view.message(game,'公共资讯','公共资讯暂不可用；请稍后再试。'))
            try:
                cap='news'
                snapshot=self.public.read(game,cap)
                self._capture_snapshot(context,None,game+':'+cap,snapshot)
                return reply(view.snapshot_card(game,'',cap,snapshot,self.asset_cache),True)
            except AccountNotFoundError:return reply(view.message(game,'公共资讯','该游戏公共资讯暂不可用。'))
        try:
            principal=self.bindings.resolve_qq_identity(identity)
        except QqBindingError:
            scene='当前群' if identity.scene=='group' else '当前私聊'
            card=view.document('status',game or 'all',scene+'尚未绑定',
                subtitle='当前会话没有有效的网站账号绑定。',
                sections=[{'title':'请在当前会话完成绑定','fields':[
                    view.field('1 登录看板','没有网站身份时，请向管理员获取邀请注册入口。'),
                    view.field('2 网站生成绑定码','进入网站 QQ 绑定页面，生成新的绑定码。'),
                    view.field('3 本会话发送绑定指令','在'+scene+'发送「绑定 实际绑定码」，收到绑定成功即完成。')]}],
                notices=['绑定完成后，重新发送「我的总览」。',
                         '公共活动可直接发送「鸣潮 活动」「异环 日历」等带游戏前缀指令。'])
            return reply(card)
        if context is not None:
            context.update(user_id=principal.user_id,binding_revision=self._binding_revision(identity))
        if self.query_service is None:return reply(view.message(game,'账号查询','账号查询服务暂不可用。'))
        try:
            account_rows=self.query_service.list_accounts(principal)
            if context is not None:context['account_rows']=account_rows
            if command in ('calendar','events','recent_events'):
                games=[]
                for current in GAME_NAMES:
                    accounts=self._accounts(principal,current,account_rows=account_rows)
                    if accounts:
                        games.append(current)
                        for _,scope in accounts:self._capture_scope(context,scope)
                if not games:return reply(view.message(None,'活动查询','暂无有效游戏授权；请在网站授权，或使用「游戏 活动」公共查询。'))
                return reply(self._public_events(games,command,context),True)
            if command=='status':
                items=[]
                for row in account_rows:
                    if row['game'] not in GAME_NAMES:continue
                    state='已授权' if row['state']=='active' else '需重新授权'
                    if row.get('query_state')=='credential_unavailable':state='授权凭据不可用，请重新授权'
                    items.append({'title':view.label(row['game'],row['provider']),
                                  'fields':[view.field('授权',state),view.field('默认账号','是' if row['is_default'] else '否')]})
                return reply(view.document('status','all','QQ 网站绑定已确认。我的账号',sections=[{'title':'授权状态','rows':items}],
                    notices=['暂无游戏账号；请在网站完成游戏授权。'] if not items else []),True)
            if command=='overview':
                selected=[];notices=[]
                for current in GAME_NAMES:
                    accounts=self._accounts(principal,current,account_rows=account_rows)
                    selected.extend(accounts)
                    if not accounts:notices.append(GAME_NAMES[current]+'暂无有效授权账号；请在网站授权。')
                sections=[]
                for row,scope in selected:
                    self._capture_scope(context,scope)
                    snapshot=self._snapshot(row,scope,'account',context,read_cache)
                    if snapshot is None:
                        notices.append(view.label(row['game'],row['provider'])+'：当前缓存不支持账号总览。');continue
                    fields=view.account_fields(row['game'],row['provider'],snapshot.payload)
                    if row['provider']!='skland':
                        stamina=self._snapshot(row,scope,'stamina',context,read_cache)
                        if stamina is not None:
                            data=view.obj(stamina.payload)
                            fields+=view.capability_section(row['game'],row['provider'],'stamina',stamina,self.asset_cache)['fields']
                            fields.append(view.time_field('体力更新时间',stamina.fetched_at))
                            if stamina.state not in ('ok','success'):fields.append(view.field('体力状态',view.metadata(stamina)[0]['value']))
                    section={'title':view.label(row['game'],row['provider']),'layout':'stats', 'fields':fields+view.metadata(snapshot)}
                    view.with_image(section,view.image_ref(self.asset_cache,row['game'],'game',row['game']))
                    sections.append(section)
                    roles=self._snapshot(row,scope,'roles',context,read_cache)
                    if roles is not None:
                        details={}
                        if row['game']=='wuthering_waves':
                            for entry in view.role_entries(row['game'],roles.payload,row['provider'])[:6]:
                                detail=self._role_detail_snapshot(scope,entry.get('role_id'),detail_cache)
                                if detail is not None:
                                    self._capture_snapshot(context,scope,'role_detail',detail)
                                    details[str(entry.get('role_id'))]=detail.payload
                        sections+=view.overview_roles(row['game'],row['provider'],roles,self.asset_cache,details=details)
                    if row['game']=='wuthering_waves':
                        calabash=self._snapshot(row,scope,'calabash',context,read_cache)
                        if calabash is not None:
                            sections.append(view.capability_section(row['game'],row['provider'],'calabash',calabash,self.asset_cache))
                card=view.document('overview','all','我的 · 三游戏总览',sections=sections,notices=notices)
                card['version']=3
                return reply(card,True)
            if game is None or game not in GAME_NAMES:return reply(view.help_document())
            selected=self._accounts(principal,game,command=command,account_rows=account_rows)
            if not selected:return reply(view.message(game,GAME_NAMES[game],GAME_NAMES[game]+'暂无有效授权账号；请在网站授权。'))
            if game=='endfield' and command in ('roles','stamina','exploration','progress'):
                selected=[item for item in selected if item[0]['provider']=='skland']
                if not selected:return reply(view.message(game,GAME_NAMES[game],
                    '此查询需要本人森空岛档案授权；鹰角寻访身份没有档案角色缓存。请在网站授权。'))
            sections=[];notices=[]
            for row,scope in selected:
                self._capture_scope(context,scope)
                if command=='refresh':
                    receipt_fields=[]
                    for cap in self.query_service.capabilities(scope):
                        receipt=self.query_service.request_refresh(scope,cap)
                        receipt_fields.append(view.field(view.LABELS.get(cap,cap),'刷新已排队' if receipt.state=='queued' else '已有刷新任务，已合并'))
                    sections.append({'title':view.label(game,row['provider']), 'fields':receipt_fields})
                    continue
                wanted=('account','stamina','gacha','record','roles') if command=='summary' else (command,)
                for cap in wanted:
                    if command=='summary' and row['provider']=='skland' and cap=='stamina':continue
                    snapshot=self._snapshot(row,scope,cap,context,read_cache)
                    nte_ledger=self._ledger_snapshot(scope,game) if cap=='gacha' and game=='nte' else None
                    if snapshot is None and nte_ledger is not None:
                        snapshot=QueryResult(None,None,'never',None)
                    if snapshot is None:
                        if command!='summary':notices.append(view.label(game,row['provider'])+'：当前缓存不支持此查询；请在网站查看已开放能力。')
                        continue
                    if cap=='gacha' and game=='nte':
                        ledger=nte_ledger
                        if ledger is not None:self._capture_snapshot(context,scope,'gacha_ledger',ledger)
                        card=view.gacha_document(game,row['provider'],snapshot,self.asset_cache,ledger=ledger)
                        if command!='summary':return reply(card,True)
                        sections+=card['sections'];notices+=card['notices'];continue
                    if cap=='roles' and command=='roles':
                        card=view.role_card(game,row['provider'],snapshot,role_name,self.asset_cache)
                        if game=='wuthering_waves' and role_name is not None and card['kind']=='detail':
                            entries=view.role_entries(game,snapshot.payload,row['provider'])
                            entry=next(item for item in entries if item.get('name')==role_name)
                            detail=self._role_detail_snapshot(scope,entry.get('role_id'),detail_cache)
                            if detail is not None:
                                self._capture_snapshot(context,scope,'role_detail',detail)
                                card['sections']+=view.wuwa_detail_sections(detail.payload,self.asset_cache)
                                card['footer']+=' · 观测时间：'+view.format_time(detail.fetched_at)
                                view.with_image(card,view.image_ref(self.asset_cache,game,'role',entry.get('role_id') or role_name,
                                    view.obj(view.obj(detail.payload).get('role')).get('role_icon_url')))
                                card['notices'].append('详情来自网站成功观测缓存；该次观测之后的变化未知。')
                            else:
                                card['notices'].append('详情未采集或不在近期缓存；请在网站查看该角色后重试。')
                        return reply(card,True)
                    if command!='summary':return reply(view.snapshot_card(game,row['provider'],cap,snapshot,self.asset_cache),command in PAGED_COMMANDS)
                    if cap=='roles':
                        card=view.role_card(game,row['provider'],snapshot,asset_cache=self.asset_cache)
                        if not card['sections'][0]['rows']:continue
                        section=card['sections'][0]
                        section['title']=view.label(game,row['provider'])+' · '+section['title']
                    else:section=view.capability_section(game,row['provider'],cap,snapshot,self.asset_cache)
                    section.setdefault('fields',[]).extend(view.metadata(snapshot))
                    sections.append(section)
            if not sections and not notices:notices=['当前授权没有可用查询能力；请在网站检查授权。']
            if command=='refresh':
                notices.append('只提交现有能力的刷新队列；查询时仍读取缓存。抽卡导入和缺失详情请在网站操作。')
            card=view.document('status' if command=='refresh' else 'summary',game,GAME_NAMES[game]+' · '+('刷新' if command=='refresh' else '总览'),
                               sections=sections,notices=notices)
            if command not in ('refresh','summary'):card['title']=GAME_NAMES[game]+' · '+view.LABELS.get(command,command)
            return reply(card,command=='summary')
        except (AccountNotFoundError,CredentialStoreError):
            return reply(view.message(game,'授权状态','授权已失效或凭据不可用；请在网站重新授权。'))
        except (HTTPException,PermissionError,ValueError):
            return reply(view.message(game,'查询状态','查询或刷新暂不可用；请在网站检查授权和服务状态。'))

    async def query_reply(self,identity,command,game=None,*,image_requested=False,budget_seconds=0,role_name=None,page=1):
        deadline=time.monotonic()+max(0,min(10,budget_seconds))
        context={}
        response=self.query(identity,command,game,image_context=context if image_requested else None,
                            role_name=role_name,page=page)
        if not context.get('card'):return response
        from .web_payload import SUPPORTED_COMMANDS, build_web_payload
        if command not in SUPPORTED_COMMANDS:return response
        if self.render_queue is None or budget_seconds<=0:
            return self._text_fallback(context['card'])
        try:
            web=build_web_payload(self,context,command,game,role_name)
        except (AccountNotFoundError,CredentialStoreError,HTTPException,PermissionError,ValueError,TypeError,KeyError,OSError):
            return self._text_fallback(context['card'])
        if web is None:return response
        grants=context['grants'];user_id=context.get('user_id')
        scope=grants[0][0] if grants else AccountScope(user_id or 'public','summary','summary')
        snapshots=context['snapshots']
        payload={'card':context['card'],'web':web,'scopes':[{'account_id':s.account_id,'role_id':s.role_id,'grant_version':version} for s,version in grants],
                 'snapshot_times':[s.fetched_at for s in snapshots], 'snapshot_fingerprints':context['fingerprints']}
        if grants:payload['grant_version']=grants[0][1]
        rendered=QueryResult(payload,max((s.fetched_at for s in snapshots if s.fetched_at),default=None),
            'ok' if all(s.state in ('ok','success') for s in snapshots) else 'stale',
            True if snapshots and all(s.complete is True for s in snapshots) else False if any(s.complete is False for s in snapshots) else None)
        try:
            png=await self.render_queue.render(scope,rendered,budget_seconds=max(0,deadline-time.monotonic()))
        except Exception:png=None
        if user_id is not None:
            try:
                principal=self.bindings.resolve_qq_identity(identity)
                if principal.user_id!=user_id or self._binding_revision(identity)!=context['binding_revision']:
                    raise AccountNotFoundError()
                for referenced,version in grants:
                    checked=self.query_service.accounts.require_scope(principal,referenced.account_id,referenced.role_id)
                    if self.query_service.accounts.describe(checked)['version']!=version:raise AccountNotFoundError()
            except (QqBindingError,AccountNotFoundError,CredentialStoreError):
                self.render_queue.renderer.invalidate_account(user_id)
                return {'text':'绑定或授权已变更；请在网站确认后重新查询。'}
        if png is not None:response['image']=base64.b64encode(png).decode('ascii')
        else:return self._text_fallback(context['card'])
        return response

    def _text_fallback(self,card):
        # A timed-out renderer may still read the original document in its worker.
        card=dict(card)
        card['notices']=card.get('notices',[])[:5]+['图片暂不可用，当前为文字摘要；完整内容请到网站查看。']
        return {'text':card_to_text(card)}


def install_qq_query_routes(app, *, app_id, dashboard_url='', urls_approved=False,frontend_dist=None):
    from game_assistant.cloud_app import allow_cloud_route
    settings=app.state.settings
    from .assets import PublicAssetCache
    asset_cache=PublicAssetCache() if settings.qq_images_enabled else None
    render_queue=RenderQueue(SummaryRenderer(frontend_dist=frontend_dist,font_path=settings.qq_image_font_path,max_bytes=settings.qq_image_max_bytes,asset_cache=asset_cache)) if settings.qq_images_enabled else None
    service=QqQueryService(app.state.qq_bindings,getattr(app.state,'account_query',None),
                           getattr(app.state,'public_query',None),dashboard_url=dashboard_url,urls_approved=urls_approved,render_queue=render_queue,asset_cache=asset_cache,
                           private_poll_seconds=settings.cloud_private_poll_seconds)
    app.state.qq_query=service
    async def query(body:QueryBody,request:Request):
        if not getattr(request.state,'service_principal',False):raise HTTPException(401,'service_auth_required')
        if body.identity.app_id!=app_id:raise HTTPException(400,'qq_app_mismatch')
        return await service.query_reply(body.identity.identity(),body.command,body.game,
            image_requested=body.image_requested,budget_seconds=body.render_budget_seconds,role_name=body.role_name,page=body.page)
    app.add_api_route('/internal/qq/query',query,methods=['POST'])
    allow_cloud_route(app,'/internal/qq/query',{'POST'},access='service')
    return service
