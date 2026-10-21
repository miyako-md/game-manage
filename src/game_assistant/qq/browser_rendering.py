"""Built shared Vue components in isolated Chromium contexts; no network/profile.

Browser and font installation are deployment prerequisites, never runtime downloads.
"""
import asyncio
from io import BytesIO
import hashlib
import json
import mimetypes
import os
import re
from pathlib import Path
import sys
import time
import uuid
from urllib.parse import urlsplit, unquote

from PIL import Image

from .assets import safe_public_url
from .rendering import SummaryRenderer, RenderingUnavailable, RenderingPageUnavailable, RenderedImage
from .a_rendering import AImageRenderer

ORIGIN = 'https://render.invalid'
KINDS = frozenset(('calendar', 'wuwa_role', 'nte_role', 'wuwa_gacha', 'nte_gacha','game_snapshot','notice','guide'))
UPLOAD_TARGET_BYTES = 256 * 1024
PAGE_WIDTH = 720
PAGE_MAX_HEIGHT = 1440
MAX_PAGES = 100


def validate_snapshot(value):
    keys = {'schema_version','kind','game','display_data','as_of','page','title','next_command','theme'}
    if not isinstance(value, dict) or set(value) != keys or value['schema_version'] != 1 or value['kind'] not in KINDS:
        raise RenderingUnavailable('qq_browser_invalid_snapshot')
    if value['game'] not in ('all','wuthering_waves','nte','endfield') or value['theme'] not in ('light','dark'):
        raise RenderingUnavailable('qq_browser_invalid_snapshot')
    if type(value['page']) is not int or not 1 <= value['page'] <= 100:
        raise RenderingUnavailable('qq_browser_invalid_snapshot')
    for key, limit in (('as_of',64),('title',128),('next_command',128)):
        if not isinstance(value[key], str) or not 1 <= len(value[key]) <= limit or not value[key].isprintable():
            raise RenderingUnavailable('qq_browser_invalid_snapshot')
    from datetime import datetime
    try: datetime.fromisoformat(value['as_of'])
    except ValueError: raise RenderingUnavailable('qq_browser_invalid_snapshot') from None
    if not isinstance(value['display_data'], dict): raise RenderingUnavailable('qq_browser_invalid_snapshot')
    expected = {'calendar':{'games','snapshots'},'wuwa_role':{'detail','fetched_at'},'nte_role':{'snapshot'},'wuwa_gacha':{'archive'},'nte_gacha':{'snapshot','ledger','roles'},'game_snapshot':{'panels','notices'},'notice':{'title','sections','notices'},'guide':{'guide'}}
    if set(value['display_data']) != expected[value['kind']]: raise RenderingUnavailable('qq_browser_invalid_snapshot')
    count = 0
    from .render_snapshot import CALENDAR, VERSION, ROLE, GACHA, DISPLAY_FIELDS, PANEL_CAPS, PROVIDERS, panel_payload
    def strings(values):
        if not isinstance(values,list) or any(not isinstance(item,str) for item in values):raise RenderingUnavailable('qq_browser_invalid_snapshot')
    if value['kind'] in ('notice','game_snapshot'):strings(value['display_data']['notices'])
    if value['kind']=='notice':
        data=value['display_data']
        if not isinstance(data['title'],str) or not isinstance(data['sections'],list):raise RenderingUnavailable('qq_browser_invalid_snapshot')
        for section in data['sections']:
            # An optional game names the game a help group belongs to (presentation only).
            if not isinstance(section,dict) or not {'title','items'}<=set(section)<={'title','items','game'} or not isinstance(section['title'],str):raise RenderingUnavailable('qq_browser_invalid_snapshot')
            if 'game' in section and section['game'] not in ('wuthering_waves','nte','endfield'):raise RenderingUnavailable('qq_browser_invalid_snapshot')
            strings(section['items'])
    if value['kind']=='game_snapshot':
        panels=value['display_data']['panels']
        if not isinstance(panels,list) or len(panels)>64:raise RenderingUnavailable('qq_browser_invalid_snapshot')
        for panel in panels:
            if not isinstance(panel,dict) or set(panel)!={'game','provider','capability','snapshot'}:raise RenderingUnavailable('qq_browser_invalid_snapshot')
            game,provider,cap=panel['game'],panel['provider'],panel['capability']
            if game not in PANEL_CAPS or provider not in PROVIDERS or cap not in PANEL_CAPS[game]:raise RenderingUnavailable('qq_browser_invalid_snapshot')
            providers=({'public'} if cap in ('events','recent_events') else {'kuro'} if game=='wuthering_waves' else {'tajiduo'} if game=='nte' else {'hypergryph','skland'})
            if game=='nte' and cap=='teams':providers={'public','tajiduo'}
            if provider not in providers:raise RenderingUnavailable('qq_browser_invalid_snapshot')
            if game=='endfield' and ((cap in ('ship','honor','operator_detail','combat') and provider!='skland') or (cap=='gacha' and provider!='hypergryph')):raise RenderingUnavailable('qq_browser_invalid_snapshot')
            row=panel['snapshot']
            if not isinstance(row,dict) or set(row)!={'payload','fetched_at','state','complete','stale'}:raise RenderingUnavailable('qq_browser_invalid_snapshot')
            if type(row['stale']) is not bool or row['complete'] is not None and type(row['complete']) is not bool or not isinstance(row['state'],str) or row['fetched_at'] is not None and not isinstance(row['fetched_at'],str):raise RenderingUnavailable('qq_browser_invalid_snapshot')
            if panel_payload(game,provider,cap,row['payload'])!=row['payload']:raise RenderingUnavailable('qq_browser_private_field')
    guide_fields=frozenset('guide key text note sourceId author version url aliases attribute element role status image sources asset_hints'.split()) if value['kind']=='guide' else frozenset()
    if value['kind']=='guide' and not isinstance(value['display_data']['guide'],dict):raise RenderingUnavailable('qq_browser_invalid_snapshot')
    display_keys=CALENDAR|VERSION|ROLE|GACHA|DISPLAY_FIELDS|guide_fields|frozenset('games snapshots game_id display_name events payload fetched_at state complete stale detail snapshot archive ledger roles wuthering_waves nte endfield all 0 1 2 3 4 5 6 S A B unknown panels game provider capability notices sections items 轻波级 巨浪级 怒涛级 海啸级'.split())
    def inspect(node, depth=0):
        nonlocal count
        count += 1
        if count > 30000 or depth > 16: raise RenderingUnavailable('qq_browser_data_limit')
        if isinstance(node, dict):
            if len(node)>128: raise RenderingUnavailable('qq_browser_data_limit')
            for key, child in node.items():
                if not isinstance(key,str) or key not in display_keys and not re.fullmatch(r'bucket_\d{1,4}',key) or len(key)>96 or any(word in key.lower() for word in ('token','password','cookie','credential','openid','account_id','user_id','authorization','uid')) and key!='guide':
                    raise RenderingUnavailable('qq_browser_private_field')
                inspect(child,depth+1)
        elif isinstance(node,list):
            if len(node)>2000: raise RenderingUnavailable('qq_browser_data_limit')
            for child in node:inspect(child,depth+1)
        elif isinstance(node,str):
            if len(node)>8000 or '\x00' in node: raise RenderingUnavailable('qq_browser_data_limit')
        elif node is not None and type(node) not in (bool,int,float):raise RenderingUnavailable('qq_browser_invalid_snapshot')
    inspect(value['display_data'])
    try:encoded=json.dumps(value,ensure_ascii=False,allow_nan=False)
    except (TypeError,ValueError):raise RenderingUnavailable('qq_browser_invalid_snapshot') from None
    if len(encoded.encode())>1024*1024:raise RenderingUnavailable('qq_browser_data_limit')
    return json.loads(encoded)


class BrowserRenderer(AImageRenderer,SummaryRenderer):
    def __init__(self, *, dist_path='', executable_path='', enabled=True, template='pages', **kwargs):
        super().__init__(**kwargs)
        if template not in ('pages','a'):raise ValueError('qq_template_invalid')
        self.template=template
        self.enabled = enabled
        self.dist = Path(dist_path).resolve() if dist_path else Path(__file__).resolve().parents[3] / 'frontend' / 'dist'
        self.executable_path=executable_path
        self._playwright=None
        self._browser=None
        self.last_state=None
        self.cleanup_seconds=2
        self.disabled_reason=None
        self._memo={}
        self._a_context=self._a_page=self._a_session=None
        self._a_build=None;self._a_images={};self._a_forbidden=[]

    async def _bounded_close(self, operation):
        task=asyncio.create_task(operation)
        done,_=await asyncio.wait({task},timeout=self.cleanup_seconds)
        if done:
            result=await asyncio.gather(task,return_exceptions=True)
            return not isinstance(result[0],BaseException)
        task.cancel()
        task.add_done_callback(lambda value: value.exception() if not value.cancelled() else None)
        return False

    async def _recycle(self):
        # Own Playwright driver process only. Killing its browser descendants is
        # a final bounded fault cleanup, never a user's installed browser/profile.
        runtime,browser=self._playwright,self._browser
        self._playwright=self._browser=None
        self._a_context=self._a_page=self._a_session=None
        self._a_build=None;self._a_images={}
        browser_closed=browser is None or await self._bounded_close(browser.close())
        runtime_closed=runtime is None or await self._bounded_close(runtime.stop())
        if browser_closed and runtime_closed:return
        process=getattr(getattr(getattr(runtime,'_impl_obj',None),'_connection',None),'_transport',None)
        process=getattr(process,'_proc',None)
        if process is None:
            self.enabled=False
            self.disabled_reason='qq_browser_cleanup_unconfirmed'
        if process is not None:
            import psutil
            try:
                owned=psutil.Process(process.pid)
                children=owned.children(recursive=True)
                for child in reversed(children):
                    try:child.kill()
                    except psutil.NoSuchProcess:pass
                owned.kill()
                _,alive=await asyncio.to_thread(psutil.wait_procs,[*children,owned],timeout=self.cleanup_seconds)
                if alive:
                    self.enabled=False
                    self.disabled_reason='qq_browser_cleanup_unconfirmed'
            except psutil.NoSuchProcess:
                # The missing driver alone does not prove orphan children stopped.
                self.enabled=False
                self.disabled_reason='qq_browser_cleanup_unconfirmed'
            except psutil.Error:
                self.enabled=False
                self.disabled_reason='qq_browser_cleanup_unconfirmed'
        if runtime is not None:await self._bounded_close(runtime.stop())

    def _unchanged(self, name, paths, compute):
        """compute() again only when a file's size, mtime, inode or type (lstat) changes.

        Hashing the build and the CJK font on every render blocked the API's event loop
        for tens of milliseconds; any replacement, including one by a link, still re-runs it.
        """
        signature=[]
        for path in paths:
            try:
                info=os.lstat(path)
                signature.append((str(path),info.st_size,info.st_mtime_ns,info.st_ino,info.st_mode))
            except OSError:
                signature.append((str(path),None))
        cached=self._memo.get(name)
        if cached and cached[0]==signature:return cached[1]
        value=compute()
        self._memo[name]=(signature,value)
        return value

    def _build(self):
        if not (self.dist/'render.html').is_file():raise RenderingUnavailable('qq_browser_build_unavailable')
        files = [self.dist/'render.html',self.dist/'render-a.html', *sorted((self.dist/'assets').glob('*')),self.dist/'render-font.woff2',self.dist/'render-font.json']
        def digest_files():
            digest=hashlib.sha256()
            for path in files:
                if path.is_file():digest.update(path.name.encode());digest.update(path.read_bytes())
            return digest.hexdigest()
        return self._unchanged('build',files,digest_files)

    def _check_font(self):
        def check():
            self._font()  # Actual CJK glyph validation, not fonts.check() fallback.
            return True
        self._unchanged('font_check',[Path(self.font_path)],check)

    def _font_resource(self):
        return self._unchanged('font_resource',[Path(self.font_path),self.dist/'render-font.woff2',self.dist/'render-font.json'],
                               self._verified_font_resource)

    def _verified_font_resource(self):
        """Use only a prepared complete-font sidecar bound to the original.

        Missing/stale/unsafe preparation always retains the configured font;
        no conversion dependency, payload glyph selection or extra I/O exists.
        """
        original=Path(self.font_path)
        fallback=(original,'font/ttf')
        woff=self.dist/'render-font.woff2';manifest=self.dist/'render-font.json'
        keys={'schema_version','source_sha256','woff2_sha256','source_bytes','woff2_bytes','glyph_count',
            'cmap_sha256','glyph_order_sha256','hmtx_sha256','outline_tag','outline_sha256','fonttools_version'}
        try:
            if any(not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(self.dist.resolve()) for path in (woff,manifest)):return fallback
            if manifest.stat().st_size>4096 or not 0<woff.stat().st_size<=64*1024*1024:return fallback
            info=json.loads(manifest.read_text(encoding='utf-8'))
            if not isinstance(info,dict) or set(info)!=keys or type(info['schema_version']) is not int or info['schema_version']!=1:return fallback
            if any(type(info[key]) is not int or info[key]<=0 for key in ('source_bytes','woff2_bytes','glyph_count')):return fallback
            if info['outline_tag'] not in ('CFF ','CFF2') or not isinstance(info['fonttools_version'],str) or not re.fullmatch(r'[0-9.]+',info['fonttools_version']):return fallback
            if any(not isinstance(info[key],str) or not re.fullmatch('[0-9a-f]{64}',info[key]) for key in ('source_sha256','woff2_sha256','cmap_sha256','glyph_order_sha256','hmtx_sha256','outline_sha256')):return fallback
            raw=original.read_bytes();encoded=woff.read_bytes()
            if len(raw)!=info['source_bytes'] or len(encoded)!=info['woff2_bytes'] or encoded[:4]!=b'wOF2':return fallback
            if hashlib.sha256(raw).hexdigest()!=info['source_sha256'] or hashlib.sha256(encoded).hexdigest()!=info['woff2_sha256']:return fallback
            return woff,'font/woff2'
        except (OSError,ValueError,TypeError):return fallback

    async def _start(self):
        if self._browser is not None and self._browser.is_connected(): return
        if self._playwright is not None:
            await self._recycle()
            if not self.enabled:raise RenderingUnavailable('qq_browser_cleanup_failed')
        try:
            from playwright.async_api import async_playwright
            self._playwright=await async_playwright().start()
            options={'headless':True}
            if sys.platform=='linux':options['chromium_sandbox']=True
            if self.executable_path:options['executable_path']=self.executable_path
            self._browser=await self._playwright.chromium.launch(**options)
        except Exception:raise RenderingUnavailable('qq_browser_runtime_unavailable') from None

    def cache_key(self, scope, result):
        base=super().cache_key(scope,result)
        font=Path(self.font_path)
        font_hash=self._unchanged('font_hash',[font],lambda:hashlib.sha256(font.read_bytes()).hexdigest() if font.is_file() else 'missing')
        from .render_snapshot import asset_requests
        assets=[(url,mode,self.asset_cache.url_fingerprint(url,artwork=mode=='artwork',portrait=mode=='portrait'))
                for url,mode in asset_requests(result.payload.get('render_snapshot'))] if self.asset_cache is not None else []
        return hashlib.sha256(json.dumps([base,self._build(),font_hash,assets,'shared-vue-v1',self.template]).encode()).hexdigest()

    async def render_summary_async(self, scope, result, *, budget_seconds):
        deadline=time.monotonic()+min(10,budget_seconds)
        snapshot=result.payload.get('render_snapshot')
        if snapshot is None:raise RenderingUnavailable('qq_browser_shared_content_unavailable')
        if not self.enabled:raise RenderingUnavailable(self.disabled_reason or 'qq_browser_disabled')
        snapshot=validate_snapshot(snapshot)
        self._check_font()
        key=self.cache_key(scope,result)
        with self.lock:
            cached=self.cache.get(key)
            if cached and cached[1]>time.monotonic():
                from .rendering import RENDER_TIMING
                if (timing:=RENDER_TIMING.get()) is not None:timing['render_cache']='hit'
                return cached[2]
            generation=self.generation
        if self.template=='a':return await self._render_a(scope,result,snapshot,deadline,key,generation)
        context=None
        if time.monotonic()>=deadline:raise RenderingUnavailable('qq_image_time_limit')
        try:
            async with asyncio.timeout(max(.001,deadline-time.monotonic())):
                await self._start()
                context=await self._browser.new_context(viewport={'width':PAGE_WIDTH,'height':PAGE_MAX_HEIGHT},device_scale_factor=1,
                    locale='zh-CN',timezone_id='Asia/Shanghai',reduced_motion='reduce',service_workers='block',accept_downloads=False)
                from .render_snapshot import asset_requests
                image_modes={}
                priority={'icon':0,'portrait':1,'artwork':2}
                for url,mode in asset_requests(snapshot):
                    if priority[mode]>=priority.get(image_modes.get(url),-1):image_modes[url]=mode
                forbidden=[]
                async def route(request):
                    url=request.request.url
                    parts=urlsplit(url)
                    if request.request.method!='GET' or request.request.resource_type in ('fetch','xhr','websocket'):
                        forbidden.append('active_request')
                        return await request.abort()
                    if url==ORIGIN+'/render-font.ttf':
                        font_path,font_type=self._font_resource()
                        return await request.fulfill(path=str(font_path),content_type=font_type)
                    if parts.scheme=='https' and parts.netloc=='render.invalid' and not parts.query and not parts.fragment:
                        path=unquote(parts.path)
                        if path=='/render.html' or path.startswith('/assets/'):
                            target=(self.dist/path.lstrip('/')).resolve()
                            if target.is_relative_to(self.dist.resolve()) and target.is_file() and target.suffix in ('.html','.js','.css','.woff2','.png','.svg'):
                                return await request.fulfill(body=target.read_bytes(),content_type=mimetypes.guess_type(target.name)[0] or 'application/octet-stream',headers={'Content-Security-Policy':"default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src https:; connect-src 'none'; frame-src 'none'; base-uri 'none'"})
                    # Only audited anonymous image URLs resolve to sanitized in-memory PNGs.
                    safe=safe_public_url(url)
                    if safe and self.asset_cache is not None and request.request.resource_type=='image':
                        mode=image_modes.get(safe,'icon')
                        png=self.asset_cache.get_url_png(safe,artwork=mode=='artwork',portrait=mode=='portrait')
                        if png is not None:
                            return await request.fulfill(body=png,content_type='image/png')
                    if request.request.resource_type!='image':forbidden.append('external_or_unexpected_resource')
                    await request.abort()
                await context.route('**/*',route)
                page=await context.new_page()
                await page.goto(ORIGIN+'/render.html',wait_until='domcontentloaded')
                fingerprint=hashlib.sha256(json.dumps(snapshot,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
                job=uuid.uuid4().hex
                await page.evaluate('(input) => window.mountRender(input)',dict(snapshot,job_id=job,input_fingerprint=fingerprint))
                state=await page.evaluate('window.__RENDER_STATE__')
                self.last_state=state
                if forbidden or state.get('state')!='ready' or state.get('job_id')!=job or state.get('input_fingerprint')!=fingerprint:raise RenderingUnavailable('qq_browser_not_ready')
                pages=state.get('pages',[])
                if not isinstance(pages,list) or not 1<=len(pages)<=MAX_PAGES:raise RenderingUnavailable('qq_browser_page_limit')
                content,displayed=state.get('content_blocks'),state.get('displayed_blocks')
                if type(content) is not int or type(displayed) is not int or content<0 or content!=displayed:
                    raise RenderingUnavailable('qq_browser_shared_content_incomplete')
                # Validate every page: returning page one must not conceal invalid later content.
                for geometry in pages:
                    if (not isinstance(geometry,dict) or type(geometry.get('width')) is not int
                        or type(geometry.get('height')) is not int or geometry['width']!=PAGE_WIDTH
                        or not 0<geometry['height']<=PAGE_MAX_HEIGHT
                        or geometry['width']*geometry['height']>self.max_pixels):
                        raise RenderingUnavailable('qq_image_pixel_limit')
                if snapshot['page']>len(pages):raise RenderingPageUnavailable(snapshot['page'],len(pages))
                box=pages[snapshot['page']-1]
                target=page.locator('.render-page').nth(snapshot['page']-1)
                png=await target.screenshot(type='png',animations='disabled')
                upload_target=min(UPLOAD_TARGET_BYTES,self.max_bytes)
                if len(png)>upload_target:
                    # Prefer smaller uploads even below the hard byte limit.
                    # Every candidate retains the whole original browser surface;
                    # missing the soft target never rejects an otherwise valid image.
                    for quality in (90,85,80):
                        optional=len(png)<=self.max_bytes
                        remaining=deadline-time.monotonic()
                        # Keep time to validate and return an already usable image.
                        if optional and remaining<=.1:break
                        try:
                            candidate=await asyncio.wait_for(target.screenshot(type='jpeg',quality=quality,animations='disabled'),
                                timeout=max(.001,remaining-(.1 if optional else 0)))
                        except Exception:
                            if not optional:raise
                            break
                        if len(candidate)<len(png):png=candidate
                        if len(png)<=upload_target:break
                with Image.open(BytesIO(png)) as image:
                    if image.size!=(box['width'],box['height']) or image.height*image.width>self.max_pixels:raise RenderingUnavailable('qq_image_pixel_limit')
                if len(png)>self.max_bytes:raise RenderingUnavailable('qq_image_size_limit')
                png=RenderedImage(png,page=snapshot['page'],total_pages=len(pages))
                with self.lock:
                    # Any account change bumps the shared generation. The caller re-checks this
                    # user's binding and grants after rendering, so the image is returned, not cached.
                    if self.generation==generation and self.cache_entries:
                        owner=(scope.user_id,frozenset([scope.account_id]+[s['account_id'] for s in result.payload.get('scopes',[])]))
                        self.cache[key]=(owner,time.monotonic()+self.cache_ttl,png)
                        while len(self.cache)>self.cache_entries:self.cache.popitem(last=False)
                return png
        finally:
            if context is not None and not await self._bounded_close(context.close()):await self._recycle()

    async def aclose(self):
        await self._recycle()
