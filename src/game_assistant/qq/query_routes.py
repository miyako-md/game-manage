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
from .commands import GAME_NAMES, PAGED_COMMANDS, MAX_PAGE, accepts, retired_reply, safe_text
from .internal_routes import IdentityBody
from .rendering import RenderQueue, RenderingPageUnavailable, RenderingUnavailable
from .cards import card_to_text
from . import presentation as view
from . import render_snapshot as shared_view


class QueryBody(BaseModel):
    model_config=ConfigDict(extra='forbid')
    identity: IdentityBody
    command: Literal['help','status','overview','summary','roles','exploration','combat','progress','gacha',
                     'calendar','events','recent_events','refresh','dashboard','resources','realestate','vehicles','teams',
                     'ship','honor','guide','retired']
    game: Literal['wuthering_waves','nte','endfield'] | None = None
    image_requested: bool = False
    render_budget_seconds: float = Field(default=0, ge=0, le=10, allow_inf_nan=False)
    role_name: str | None = Field(default=None, min_length=1, max_length=64)
    page: int = Field(default=1, ge=1, le=MAX_PAGE, strict=True)
    retired: str | None = Field(default=None, max_length=32)

    @model_validator(mode='after')
    def selectors_only(self):
        if self.role_name is not None and (self.command not in ('roles','guide') or self.game is None or not self.role_name.isprintable()):
            raise ValueError('named_role_only')
        if self.page!=1 and self.command not in PAGED_COMMANDS:
            raise ValueError('page_not_supported')
        if self.command=='overview' and self.game is not None:
            raise ValueError('overview_all_games')
        if self.command=='retired':
            if not retired_reply(self.retired,self.game):raise ValueError('retired_command_unknown')
        elif self.retired is not None or not accepts(self.command,self.game):
            raise ValueError('command_not_available')
        return self


class QqQueryService:
    def __init__(self, bindings, query, public, *, dashboard_url='', urls_approved=False, render_queue=None,asset_cache=None,clock=None):
        self.bindings,self.query_service,self.public=bindings,query,public
        self.dashboard_url,self.urls_approved=dashboard_url,urls_approved
        self.render_queue=render_queue
        self.asset_cache=asset_cache
        self.clock=clock or (lambda:datetime.now(view.BEIJING))
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

    def _accounts(self,principal,game,*,metadata_only=False):
        # A cache-only supplemental view must not resolve runtime capabilities:
        # AccountQuery.list_accounts() also loads grants while decorating rows.
        reader=self.query_service.accounts.list_accounts if metadata_only else self.query_service.list_accounts
        rows=[r for r in reader(principal)
              if r['game']==game and r['state']=='active' and r['roles']]
        providers=('hypergryph','skland') if game=='endfield' else ('kuro',) if game=='wuthering_waves' else ('tajiduo',)
        selected=[]
        for provider in providers:
            candidates=[r for r in rows if r['provider']==provider]
            if not candidates:continue
            row=min(candidates,key=lambda r:(not bool(r['is_default']),r['account_id']))
            role=min(row['roles'],key=lambda r:(not bool(r['is_default']),r['role_id']))
            scope=self.query_service.accounts.require_scope(principal,row['account_id'],role['role_id'])
            selected.append((row,scope))
        return selected

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
        info=self.query_service.accounts.describe(scope)
        context['grants'].append((scope,info['version']))
        context['grant_ids'][scope]=info.get('grant_id')

    def _capture_snapshot(self, context, scope, cap, snapshot):
        if context is None:return
        identity=(scope.user_id,scope.account_id,scope.role_id) if scope else ('public',)
        grant_id=context['grant_ids'].get(scope) if scope is not None else None
        encoded=json.dumps([identity,grant_id,cap,snapshot.payload,snapshot.fetched_at,snapshot.state,snapshot.complete],
                           ensure_ascii=False,sort_keys=True,default=str).encode()
        context['snapshots'].append(snapshot)
        context['fingerprints'].append(hashlib.sha256(encoded).hexdigest())

    def _reply(self, card, page, context):
        presentation_card=card
        card=view.long_document(card,1 if context is not None else page,asset_cache=self.asset_cache)
        if context is not None:
            context['card']=card
            if context.get('render_snapshot') is None:
                if context.get('panels'):
                    context['render_snapshot']=shared_view.game_snapshot(context['panels'],self.clock(),page,title=presentation_card['title'],
                        command=context['next_command'],notices=context.get('panel_notices',[])+context.get('shared_notices',presentation_card.get('notices',[])))
                else:context['render_snapshot']=shared_view.notice_snapshot(presentation_card,self.clock(),page,command=context['next_command'])
            if context['render_snapshot']['kind'] not in ('wuwa_role','nte_role'):
                context['render_snapshot']['next_command']=context['next_command']
        return {'text':card_to_text(card)}

    def _panel(self,context,row,cap,snapshot,*,summary=False,resolved=None):
        if context is None or cap not in shared_view.PANEL_CAPS.get(row['game'],{}):return
        context['panels'].append(shared_view.game_panel(row['game'],row['provider'],cap,snapshot,summary=summary,resolved=resolved))
        if summary and cap=='roles':context['panel_notices'].append(GAME_NAMES[row['game']]+'总览最多展示 6 名角色；完整角色请使用角色指令。')

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

    def _role_detail_snapshot(self, scope, character_id):
        private=getattr(self.query_service,'private',None)
        if private is None or character_id is None:return None
        root=getattr(private,'private_root',None)
        if root is not None:
            from game_assistant.private_data import scope_directory
            if not (scope_directory(root,scope)/'wuwa_history'/'ledger.sqlite3').is_file():return None
        # Fixed recent-observation window; no upstream lookup or arbitrary SQL.
        history=private.ledger(scope,'wuwa_history').read(scope,'role_detail',100,0)
        found=next((item for item in view.rows(view.obj(history).get('items'))
                    if str(item.get('subject'))==str(character_id)),None)
        if found is None:return None
        payload=view.obj(found.get('payload'))
        if str(payload.get('character_id'))!=str(character_id):return None
        return QueryResult(view.obj(payload.get('data')),found.get('observed_at') or found.get('source_at') or found.get('archived_at'),
                           'ok',False)

    def _endfield_operator_snapshot(self,scope,char_id):
        private=getattr(self.query_service,'private',None)
        reader=getattr(private,'cached_skland_operator',None)
        if reader is None or not isinstance(char_id,str) or not char_id:
            return None
        cached=reader(scope,char_id)
        if not isinstance(cached,dict):
            return None
        operator=cached.get('operator')
        if operator is not None and (not isinstance(operator,dict) or operator.get('id')!=char_id):
            return None
        state='error' if cached.get('stale') or cached.get('error') or operator is None else 'ok'
        return QueryResult(operator,cached.get('fetched_at'),state,None)

    def _snapshot(self,row,scope,cap,context,cache=None):
        game,provider=row['game'],row['provider']
        caps=self.query_service.capabilities(scope)
        # Skland account snapshots contain observed subviews; no extra fetch.
        embedded=provider=='skland' and cap in ('roles','stamina','exploration','progress') and 'account' in caps
        actual='account' if embedded else cap
        if cap=='gacha' and provider!='skland' and game!='nte':
            ledger=self._ledger_snapshot(scope,game)
            if ledger is not None:
                if game=='endfield':
                    # The ledger's successful scan times are independent of
                    # the latest poll attempt. Preserve a known failed poll,
                    # and do not invent success when status was never observed.
                    source=self.query_service.read(scope,cap) if cap in caps else None
                    ledger=QueryResult(ledger.payload,ledger.fetched_at,source.state if source else 'unknown',ledger.complete)
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

    def _endfield_challenge_document(self,selected,context):
        if context is not None:context['shared_notices']=[]
        from game_assistant.endfield_challenges import CHALLENGE_KINDS, build_challenge_report
        from .endfield_presentation import challenge_document
        selected=[item for item in selected if item[0]['provider']=='skland']
        if not selected:
            return view.message('endfield','终末地 · 挑战','挑战需要本人森空岛档案授权；请先在网站授权并查看挑战分类。')
        row,scope=selected[0]
        self._capture_scope(context,scope)
        reader=getattr(getattr(self.query_service,'private',None),'cached_skland_challenge',None)
        reports=[]
        for kind in CHALLENGE_KINDS:
            cached=reader(scope,kind) if reader is not None else None
            report=build_challenge_report(cached,kind=kind)
            reports.append(report)
            snapshot=QueryResult(report,report['fetched_at'],
                'error' if report['stale'] else 'ok' if report['available'] else 'never',None)
            self._capture_snapshot(context,scope,'challenge:'+kind,snapshot)
        observation=QueryResult({'reports':reports},max((r['fetched_at'] for r in reports if r['fetched_at']),default=None),
            'error' if any(r['stale'] for r in reports) else 'ok',None)
        self._panel(context,row,'combat',observation)
        return challenge_document(reports)

    def _public_events(self,games,command,context,page=1):
        from .event_views import event_document
        snapshots={}
        for current in games:
            try:
                snapshot=self.public.read(current,'events') if self.public is not None else QueryResult(None,None,'never',None)
            except (AccountNotFoundError,HTTPException,ValueError,RuntimeError,OSError):snapshot=QueryResult(None,None,'error',None)
            self._capture_snapshot(context,None,current+':events',snapshot)
            if context is not None:
                try:
                    news=self.public.read(current,'news') if self.public is not None else QueryResult(None,None,'never',None)
                except (AccountNotFoundError,HTTPException,ValueError,RuntimeError,OSError):news=QueryResult(None,None,'error',None)
                self._capture_snapshot(context,None,current+':news',news)
                snapshot=shared_view.events_with_artwork(snapshot,news)
            snapshots[current]=snapshot
        if context is not None:
            context['render_snapshot']=shared_view.calendar_snapshot(snapshots,self.clock(),page) if command=='calendar' else shared_view.filtered_events_snapshot(snapshots,command,self.clock(),page)
        return event_document(command,snapshots,now=self.clock(),asset_cache=self.asset_cache)

    def _endfield_document(self, selected, command, context, cache, role_name=None):
        """Project each default provider independently; never join game identities."""
        from . import endfield_presentation as endfield
        # Shared website components carry their own coverage/state text. Legacy
        # text-card image budgets must never describe this complete Vue image.
        if context is not None:context['shared_notices']=[]
        account_commands = ('roles','exploration','ship','honor')
        if command in account_commands:
            selected = [item for item in selected if item[0]['provider']=='skland']
            if not selected:
                return view.message('endfield','终末地','此查询需要本人森空岛档案授权；鹰角寻访身份没有档案角色缓存。请在网站授权。')
        elif command=='gacha':
            selected = [item for item in selected if item[0]['provider']=='hypergryph']
            if not selected:
                return view.message('endfield','终末地 · 寻访战报','此查询需要本人鹰角寻访授权；森空岛档案不提供寻访账本。请在网站授权。')
        sections=[];notices=[]
        if command=='summary':
            if not any(row['provider']=='skland' for row,_ in selected):
                notices.append('尚未授权森空岛档案；理智、干员与建设数据需在网站授权后采集。')
        for row,scope in selected:
            self._capture_scope(context,scope)
            if row['provider']=='skland':
                snapshot=self._snapshot(row,scope,'account',context,cache)
                if snapshot is None:
                    notices.append('森空岛档案尚无可用账号缓存；请在网站采集。');continue
                from game_assistant.endfield_reports import build_endfield_report
                raw=view.obj(snapshot.payload)
                projected=QueryResult({**raw,'report':build_endfield_report(raw,fetched_at=snapshot.fetched_at)},
                    snapshot.fetched_at,snapshot.state,snapshot.complete)
                if command=='roles' and role_name is not None:
                    matches=[entry for entry in view.role_entries('endfield',snapshot.payload,'skland') if entry.get('name')==role_name]
                    detail=None
                    if len(matches)==1:
                        detail=self._endfield_operator_snapshot(scope,matches[0].get('id'))
                        if detail is not None:self._capture_snapshot(context,scope,'operator_detail',detail)
                    if len(matches)==1:
                        basic=matches[0]
                        operator={**view.obj(detail.payload if detail is not None else basic)}
                        for key in ('id','name','char_id','level','rarity','potential','evolve_phase','profession','property','avatar_url','obtained_at'):
                            if key in basic:operator[key]=basic[key]
                        selected_profile={**raw,'operators':[basic]}
                        data={**selected_profile,'report':build_endfield_report(selected_profile,fetched_at=snapshot.fetched_at),
                              'operator_detail':operator,'operator_detail_id':str(basic.get('id') or ''),
                              'operator_fetched_at':detail.fetched_at if detail is not None else None,
                              'operator_stale':detail.state not in ('ok','success') if detail is not None else False}
                        self._panel(context,row,'operator_detail',QueryResult(data,snapshot.fetched_at,snapshot.state,snapshot.complete))
                    return endfield.operator_document(snapshot,role_name,self.asset_cache,detail=detail)
                self._panel(context,row,'account' if command=='summary' else command,projected)
                builder={'roles':endfield.training_document,'exploration':endfield.regions_document,
                         'ship':endfield.ship_document,'honor':endfield.honor_document}.get(command)
                card=builder(snapshot,self.asset_cache) if builder else endfield.overview_document(snapshot,self.asset_cache)
                if command!='summary':return card
                card['sections'][0]['fields']+=view.metadata(snapshot)
                sections=card['sections']+sections;notices+=card['notices']
            else:
                snapshot=self._snapshot(row,scope,'gacha',context,cache)
                if snapshot is not None:
                    from game_assistant.endfield_reports import build_gacha_report
                    projected=QueryResult({**view.obj(snapshot.payload),'report':build_gacha_report(snapshot.payload)},snapshot.fetched_at,snapshot.state,snapshot.complete)
                    self._panel(context,row,'gacha',projected)
                    card=endfield.gacha_document(snapshot,self.asset_cache,compact=command=='summary')
                    if command=='gacha':return card
                    sections+=card['sections'][:1]
                account=self._snapshot(row,scope,'account',context,cache) if command=='summary' else None
                if account is not None:
                    sections.append({'title':'鹰角寻访 · 独立授权身份','layout':'stats',
                                     'fields':view.account_fields('endfield','hypergryph',account.payload)+view.metadata(account)})
                if snapshot is None:notices.append('鹰角寻访尚无已采集账本；请在网站同步本人记录。')
        if command=='summary':
            notices=['森空岛与鹰角寻访按独立授权分区；未核实同一角色时不拼接账号身份。']+list(dict.fromkeys(notices))[:3]
            if context is not None:context['shared_notices']=notices
        return view.document('summary','endfield','终末地 · 今日总览' if command=='summary' else '终末地 · 查询状态',
            sections=sections,notices=notices,footer='时间均为北京时间')

    def query(self,identity,command,game=None,*,image_context=None,role_name=None,page=1,retired=None):
        context=image_context
        read_cache={}
        if context is not None:
            labels={'help':'帮助','status':'状态','overview':'总览','summary':'查询','roles':'角色',
                    'exploration':'探索','combat':'挑战','progress':'进度','gacha':'抽卡','calendar':'日历','events':'活动',
                    'recent_events':'近期活动','refresh':'刷新','resources':'资源','realestate':'房产','vehicles':'车辆','teams':'队伍',
                    'ship':'帝江号','honor':'光荣之路','guide':'攻略','retired':'帮助'}
            continuation=(GAME_NAMES[game]+' ' if game is not None and command not in ('overview','status') else '')+labels.get(command,command)
            if role_name is not None:continuation+=' '+role_name
            context.update(grants=[],grant_ids={},snapshots=[],fingerprints=[],user_id=None,panels=[],panel_notices=[],shared_required=True,
                           next_command=continuation)
        reply=lambda card:self._reply(card,page,context)
        if command=='retired':
            # Fixed notice only: no binding, account or public-source read.
            return reply(view.message(game,'指令已下线',retired_reply(retired,game)))
        if command=='help':
            card=view.help_document(game)
            return reply(card)
        if command=='guide':
            from .guides import reply as guide_reply
            card,snapshot=guide_reply(game,role_name,self.clock(),page)
            if context is not None:context['render_snapshot']=snapshot
            self._capture_snapshot(context,None,'guides',QueryResult(snapshot['display_data'],None,'ok',None))
            return reply(card)
        if command=='dashboard':
            value=self.dashboard_url if self.urls_approved and self.dashboard_url else '看板网址尚未启用；请通过已保存的网站入口查看。'
            return {'text':safe_text(value,urls_approved=self.urls_approved)}
        if command in ('calendar','events','recent_events') and game is not None:
            return reply(self._public_events([game],command,context,page))
        if command=='teams' and game=='nte':
            # Public official recommendations must not be read through an
            # account capability list, which excludes PUBLIC_CAPABILITIES.
            if self.public is None:
                return reply(view.message(game,'官方配队推荐','官方配队缓存尚未采集。'))
            try:
                snapshot=self.public.read(game,'teams')
                self._capture_snapshot(context,None,game+':teams',snapshot)
                if context is not None:self._panel(context,{'game':game,'provider':'public'},'teams',snapshot)
                return reply(view.snapshot_card(game,'','teams',snapshot,self.asset_cache))
            except AccountNotFoundError:
                return reply(view.message(game,'官方配队推荐','官方配队缓存暂不可用。'))
        try:
            principal=self.bindings.resolve_qq_identity(identity)
        except QqBindingError:
            scene='当前群' if identity.scene=='group' else '当前私聊'
            card=view.document('status',game or 'all',scene+'尚未绑定',
                sections=[{'title':'请在当前会话完成绑定','fields':[
                    view.field('1 登录看板','没有网站身份时，请向管理员获取邀请注册入口。'),
                    view.field('2 网站生成绑定码','进入网站 QQ 绑定页面，生成新的绑定码。'),
                    view.field('3 本会话发送绑定指令','在'+scene+'发送「绑定 实际绑定码」，收到绑定成功即完成。')]}],
                notices=['公共活动可直接发送「鸣潮 活动」「异环 日历」等带游戏前缀指令。'])
            return reply(card)
        if context is not None:
            context.update(user_id=principal.user_id,binding_revision=self._binding_revision(identity))
        if self.query_service is None:return reply(view.message(game,'账号查询','账号查询服务暂不可用。'))
        try:
            if command in ('calendar','events','recent_events'):
                games=[]
                for current in GAME_NAMES:
                    accounts=self._accounts(principal,current)
                    if accounts:
                        games.append(current)
                        for _,scope in accounts:self._capture_scope(context,scope)
                if not games:return reply(view.message(None,'活动查询','暂无有效游戏授权；请在网站授权，或使用「游戏 活动」公共查询。'))
                return reply(self._public_events(games,command,context,page))
            if command=='status':
                account_rows=self.query_service.list_accounts(principal)
                items=[]
                for row in account_rows:
                    if row['game'] not in GAME_NAMES:continue
                    state='已授权' if row['state']=='active' else '需重新授权'
                    if row.get('query_state')=='credential_unavailable':state='授权凭据不可用，请重新授权'
                    items.append({'title':view.label(row['game'],row['provider']),
                                  'fields':[view.field('授权',state),view.field('默认账号','是' if row['is_default'] else '否')]})
                return reply(view.document('status','all','QQ 网站绑定已确认。我的账号',sections=[{'title':'授权状态','rows':items}],
                    notices=['暂无游戏账号；请在网站完成游戏授权。'] if not items else []))
            if command=='overview':
                selected=[];notices=[]
                for current in GAME_NAMES:
                    accounts=self._accounts(principal,current)
                    selected.extend(accounts)
                    if not accounts:notices.append(GAME_NAMES[current]+'暂无有效授权账号；请在网站授权。')
                sections=[]
                for row,scope in selected:
                    self._capture_scope(context,scope)
                    snapshot=self._snapshot(row,scope,'account',context,read_cache)
                    if snapshot is None:
                        notices.append(view.label(row['game'],row['provider'])+'：当前缓存不支持账号总览。');continue
                    self._panel(context,row,'account',snapshot)
                    fields=view.account_fields(row['game'],row['provider'],snapshot.payload)
                    if row['provider']!='skland':
                        stamina=self._snapshot(row,scope,'stamina',context,read_cache)
                        if stamina is not None:
                            self._panel(context,row,'stamina',stamina)
                            fields+=view.capability_section(row['game'],row['provider'],'stamina',stamina,self.asset_cache)['fields']
                            fields.append(view.time_field('体力更新时间',stamina.fetched_at))
                            if stamina.state not in ('ok','success'):fields.append(view.field('体力状态',view.metadata(stamina)[0]['value']))
                    section={'title':view.label(row['game'],row['provider']),'layout':'stats', 'fields':fields+view.metadata(snapshot)}
                    view.with_image(section,view.image_ref(self.asset_cache,row['game'],'game',row['game']))
                    sections.append(section)
                    roles=self._snapshot(row,scope,'roles',context,read_cache)
                    if roles is not None:
                        self._panel(context,row,'roles',roles,summary=True)
                        details={}
                        if row['game']=='wuthering_waves':
                            for entry in view.role_entries(row['game'],roles.payload,row['provider'])[:6]:
                                detail=self._role_detail_snapshot(scope,entry.get('role_id'))
                                if detail is not None:
                                    self._capture_snapshot(context,scope,'role_detail',detail)
                                    details[str(entry.get('role_id'))]=detail.payload
                        sections+=view.overview_roles(row['game'],row['provider'],roles,self.asset_cache,details=details)
                    if row['game']=='wuthering_waves':
                        calabash=self._snapshot(row,scope,'calabash',context,read_cache)
                        if calabash is not None:
                            self._panel(context,row,'calabash',calabash)
                            sections.append(view.capability_section(row['game'],row['provider'],'calabash',calabash,self.asset_cache))
                card=view.document('overview','all','我的 · 三游戏总览',sections=sections,notices=notices)
                card['version']=3
                return reply(card)
            if game is None or game not in GAME_NAMES:return reply(view.help_document())
            challenge=game=='endfield' and command=='combat'
            selected=self._accounts(principal,game,metadata_only=challenge)
            if not selected:return reply(view.message(game,GAME_NAMES[game],GAME_NAMES[game]+'暂无有效授权账号；请在网站授权。'))
            if challenge:return reply(self._endfield_challenge_document(selected,context))
            if game=='endfield' and command in ('summary','roles','exploration','ship','gacha','honor'):
                return reply(self._endfield_document(selected,command,context,read_cache,role_name))
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
                        if command!='summary':
                            if context is not None:context['render_snapshot']=shared_view.gacha_snapshot(game,snapshot,self.clock(),page,ledger=ledger)
                            return reply(card)
                        self._panel(context,row,cap,snapshot,summary=True)
                        sections+=card['sections'];notices+=card['notices'];continue
                    if cap=='roles' and command=='roles':
                        resolution=view.resolve_role(game,row['provider'],snapshot,role_name) if role_name is not None else None
                        card=view.role_card(game,row['provider'],snapshot,role_name,self.asset_cache,resolution=resolution)
                        detail=None
                        if game=='wuthering_waves' and role_name is not None and card['kind']=='detail':
                            entry=resolution['entry']
                            detail=self._role_detail_snapshot(scope,entry.get('role_id'))
                            if detail is not None:
                                self._capture_snapshot(context,scope,'role_detail',detail)
                                card['sections']+=view.wuwa_detail_sections(detail.payload,self.asset_cache)
                                card['footer']+=' · 观测时间：'+view.format_time(detail.fetched_at)
                                view.with_image(card,view.image_ref(self.asset_cache,game,'role',entry.get('role_id') or role_name,
                                    view.obj(view.obj(detail.payload).get('role')).get('role_icon_url')))
                                card['notices'].append('详情来自网站成功观测缓存；该次观测之后的变化未知。')
                            else:
                                card['notices'].append('详情未采集或不在近期缓存；请在网站查看该角色后重试。')
                        if context is not None:
                            projected=snapshot
                            if game=='nte' and resolution is not None and resolution['status']=='resolved':
                                projected=QueryResult({'schema_version':1,'entries':[resolution['entry']]},snapshot.fetched_at,snapshot.state,snapshot.complete)
                            if resolution is None or resolution['status']=='resolved':
                                from ..assessment_projection import with_assessment
                                assessment_store=getattr(self.query_service,'assessments',None)
                                projected=with_assessment(projected,assessment_store,scope,game) if game=='nte' and resolution is not None else projected
                                detail=with_assessment(detail,assessment_store,scope,game) if game=='wuthering_waves' else detail
                                self._capture_snapshot(context,scope,'assessment',detail if detail is not None else projected)
                                from ..character_search import character_id
                                context['render_snapshot']=shared_view.role_snapshot(game,projected,self.clock(),page,detail=detail,
                                    resolved_id=character_id(resolution['entry']) if resolution is not None else None)
                                if context['render_snapshot'] is None:
                                    self._panel(context,row,cap,projected,resolved=resolution['entry'] if resolution is not None else None)
                        return reply(card)
                    if command=='gacha' and context is not None:
                        context['render_snapshot']=shared_view.gacha_snapshot(game,snapshot,self.clock(),page)
                    self._panel(context,row,cap,snapshot,summary=(command=='summary' and cap!='roles'))
                    if command!='summary':return reply(view.snapshot_card(game,row['provider'],cap,snapshot,self.asset_cache))
                    if cap=='roles':
                        card=view.role_card(game,row['provider'],snapshot,asset_cache=self.asset_cache)
                        if not card['sections'][0]['rows']:continue
                        section=card['sections'][0]
                        section['title']=view.label(game,row['provider'])+' · '+section['title']
                    else:section=view.capability_section(game,row['provider'],cap,snapshot,self.asset_cache)
                    section.setdefault('fields',[]).extend(view.metadata(snapshot))
                    sections.append(section)
                if command=='summary' and game=='wuthering_waves' and context is not None:
                    calabash=self._snapshot(row,scope,'calabash',context,read_cache)
                    if calabash is not None:self._panel(context,row,'calabash',calabash)
            if not sections and not notices:notices=['当前授权没有可用查询能力；请在网站检查授权。']
            if command=='refresh':
                notices.append('只提交现有能力的刷新队列；查询时仍读取缓存。抽卡导入和缺失详情请在网站操作。')
            card=view.document('status' if command=='refresh' else 'summary',game,GAME_NAMES[game]+' · '+('刷新' if command=='refresh' else '总览'),
                               sections=sections,notices=notices)
            if command not in ('refresh','summary'):card['title']=GAME_NAMES[game]+' · '+view.LABELS.get(command,command)
            return reply(card)
        except (AccountNotFoundError,CredentialStoreError):
            return reply(view.message(game,'授权状态','授权已失效或凭据不可用；请在网站重新授权。'))
        except (HTTPException,PermissionError,ValueError,shared_view.RenderingUnavailable):
            return reply(view.message(game,'查询状态','查询或刷新暂不可用；请在网站检查授权和服务状态。'))

    async def query_reply(self,identity,command,game=None,*,image_requested=False,budget_seconds=0,role_name=None,page=1,retired=None):
        deadline=time.monotonic()+max(0,min(10,budget_seconds))
        context={}
        try:
            response=self.query(identity,command,game,image_context=context if image_requested else None,
                                role_name=role_name,page=page,retired=retired)
        except RenderingUnavailable:
            # Public projections run before private-account lookup. A rejected
            # full input must not become an HTTP 500 or a truncated image.
            return {'text':'完整内容超出 QQ 图片处理限制或暂时无法生成图片，未截断；请到看板查看。'}
        if not context.get('card'):return response
        if self.render_queue is None or budget_seconds<=0:
            return self._text_fallback(context['card'])
        grants=context['grants'];user_id=context.get('user_id')
        scope=grants[0][0] if grants else AccountScope(user_id or 'public','summary','summary')
        snapshots=context['snapshots']
        payload={'card':context['card'],'scopes':[{'account_id':s.account_id,'role_id':s.role_id,'grant_version':version} for s,version in grants],
                 'snapshot_times':[s.fetched_at for s in snapshots], 'snapshot_fingerprints':context['fingerprints']}
        if context.get('shared_required'):payload['shared_required']=True
        if context.get('render_snapshot') is not None:payload['render_snapshot']=context['render_snapshot']
        if grants:payload['grant_version']=grants[0][1]
        rendered=QueryResult(payload,max((s.fetched_at for s in snapshots if s.fetched_at),default=None),
            'ok' if all(s.state in ('ok','success') for s in snapshots) else 'stale',
            True if snapshots and all(s.complete is True for s in snapshots) else False if any(s.complete is False for s in snapshots) else None)
        if self.asset_cache is not None:
            remaining=max(0,deadline-time.monotonic())
            try:
                refs=[self.asset_cache.register_url(url,artwork=mode=='artwork',portrait=mode=='portrait') for url,mode in shared_view.asset_requests(context['render_snapshot'])] if context.get('render_snapshot') is not None else list(view.asset_refs(context['card']))
                refs=list(dict.fromkeys(ref for ref in refs if ref))
                await self.asset_cache.prefetch(refs,budget_seconds=min(5,remaining*0.5))
            except Exception:
                # Assets may fail independently; resolved in-memory images remain usable.
                pass
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
                    current=self.query_service.accounts.describe(checked)
                    if current['version']!=version or current.get('grant_id')!=context['grant_ids'][referenced]:
                        raise AccountNotFoundError()
            except (QqBindingError,AccountNotFoundError,CredentialStoreError):
                self.render_queue.renderer.invalidate_account(user_id)
                return {'text':'绑定或授权已变更；请在网站确认后重新查询。'}
        if isinstance(png,RenderingPageUnavailable):
            return {'text':f'请求第 {png.page} 页超出范围；当前共 {png.total_pages} 页。请查询 1–{png.total_pages} 页。'}
        if isinstance(png,RenderingUnavailable):
            if str(png) in ('qq_image_pixel_limit','qq_image_size_limit'):
                content='完整日历图片' if command=='calendar' else '完整图片'
                return {'text':content+'超出 QQ 图片尺寸或大小限制，未截断；请到看板查看。'}
            return self._text_fallback(context['card'])
        if png is None:return self._text_fallback(context['card'])
        if getattr(png,'total_pages',1)>1 and command not in PAGED_COMMANDS:
            # Action replies cannot expose a continuation that repeats the action.
            return self._text_fallback(context['card'])
        # The bot sends only the image; the full card text is what it falls back to if delivery fails.
        response['image']=base64.b64encode(png).decode('ascii')
        response['page']=getattr(png,'page',page)
        response['total_pages']=getattr(png,'total_pages',1)
        if response['total_pages']>1:
            continuation=f"第 {response['page']} / {response['total_pages']} 页"
            if response['page']<response['total_pages']:
                next_command=context['render_snapshot']['next_command']
                continuation+=f"；下一页：{next_command} {response['page']+1}"
            response['text']+='\n'+continuation
        return response

    def _text_fallback(self,card):
        # A timed-out renderer may still read the original document in its worker.
        card=dict(card)
        card['notices']=card.get('notices',[])[:5]+['图片暂不可用，改发文字版；完整内容请到网站查看。']
        return {'text':card_to_text(card)}


def install_qq_query_routes(app, *, app_id, dashboard_url='', urls_approved=False):
    from game_assistant.cloud_app import allow_cloud_route
    settings=app.state.settings
    from .assets import PublicAssetCache
    from pathlib import Path
    cache_directory=Path(settings.cloud_data_root).parent/'qq-public-assets' if settings.cloud_data_root else None
    asset_cache=PublicAssetCache(dns_resolver=settings.qq_asset_dns_resolver,cache_entries=256,cache_bytes=32*1024*1024,prefetch_tasks=192,disk_directory=cache_directory) if settings.qq_images_enabled else None
    from .browser_rendering import BrowserRenderer
    render_queue=RenderQueue(BrowserRenderer(font_path=settings.qq_image_font_path,max_bytes=settings.qq_image_max_bytes,asset_cache=asset_cache,
        enabled=settings.qq_browser_render_enabled,dist_path=settings.qq_browser_render_dist_path,
        executable_path=settings.qq_browser_render_executable_path,template='a')) if settings.qq_images_enabled else None
    service=QqQueryService(app.state.qq_bindings,getattr(app.state,'account_query',None),
                           getattr(app.state,'public_query',None),dashboard_url=dashboard_url,urls_approved=urls_approved,render_queue=render_queue,asset_cache=asset_cache)
    app.state.qq_query=service
    async def query(body:QueryBody,request:Request):
        if not getattr(request.state,'service_principal',False):raise HTTPException(401,'service_auth_required')
        if body.identity.app_id!=app_id:raise HTTPException(400,'qq_app_mismatch')
        groups=getattr(app.state,'qq_group_settings',None)
        image_requested=groups.consume(body.identity.identity(),body.game,body.command,body.image_requested) if groups else body.image_requested
        return await service.query_reply(body.identity.identity(),body.command,body.game,
            image_requested=image_requested,budget_seconds=body.render_budget_seconds,role_name=body.role_name,page=body.page,retired=body.retired)
    app.add_api_route('/internal/qq/query',query,methods=['POST'])
    allow_cloud_route(app,'/internal/qq/query',{'POST'},access='service')
    return service
