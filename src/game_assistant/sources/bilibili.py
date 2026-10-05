"""Bilibili official notices: conservative classification and bounded backfill."""
import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone

from game_assistant.event_calendar import BEIJING_TZ as BJ

logger = logging.getLogger(__name__)
RULE_VERSION = 6
REASONS = {'accepted': '有明确日期的游戏内通知', 'video': '视频或转发视频',
           'lottery': '抽奖或开奖', 'promotion': '宣传展示或社区内容',
           'no_date': '正文没有可确认的日期', 'not_ingame': '非游戏内通知',
           'incomplete': '正文不完整，待核对', 'unsupported': '不支持的动态类型'}
PROMOTION = re.compile(r'(?<![A-Za-z])(?:PV|EP|MV|OST)(?![A-Za-z])|实机(?:演示|展示|战斗)|战斗演示|时装展示|海特洛衣橱|角色档案|档案回顾|寰宇人类注疏|巡游巴士|周边通贩|网页活动|海特洛档案|闲趣时光|外观展示|角色(?:演示|展示)|宣传片|先导片|概念动画|主题曲|原声(?:音乐|专辑)|直播(?:预告|预约|活动|间)|开播预告|前瞻(?:特别)?节目|同人|创作(?:征集|激励)|线下活动|漫展|ChinaJoy|参展|壁纸|周边(?:展示|售卖|上新) ', re.I | re.X)
INGAME = re.compile(r'版本|更新|维护|停服|活动|卡池|盲盒|招募|寻访|召唤|调频|签到|限时(?:开放|开启)|补偿')
NOTICE_TITLE = re.compile(r'(?:停服|更新|维护).*(?:公告|通知)|(?:棋盘|研募|卡池).*(?:开启|返场|公告)|(?:活动|路线).*(?:开启|开放)|限定.+返场'
                          r'|\d+(?:\.\d+)+\s*版本(?:内容说明|更新公告)'
                          # 终末地：版本说明正文常含“网页活动”等词，靠标题豁免宣传词过滤。
                          r'|「[^」]+」版本(?:更新说明|更新维护预告|预下载与更新预告)|「[^」]+」(?:特许|特殊|重构)寻访|「[^」]+申领」')
DATE = re.compile(r'(?<![\dA-Za-z.])(?:(20\d{2})[年./-])?(\d{1,2})(?:月|[/-])(\d{1,2})(?:日|号)?(?:\s*(\d{1,2})[:：](\d{2}))?(?!\d)')

class SourceError(Exception):
    def __init__(self, message='', *, http_status=None, business_code=None):
        super().__init__(message)
        # Never retain SDK exceptions, response bodies, or arbitrary attributes.
        self.http_status = http_status if type(http_status) is int and 100 <= http_status <= 599 else None
        self.business_code = business_code if type(business_code) is int and -(2**31) <= business_code < 2**31 else None

def _body(item):
    dynamic = (item.get('modules') or {}).get('module_dynamic') or {}
    major = dynamic.get('major') or {}
    opus = major.get('opus') or major.get('article') or {}
    summary = opus.get('summary') or {}
    desc = dynamic.get('desc') or {}
    parts = [opus.get('title'), desc.get('text'), summary.get('text')]
    if major.get('type') == 'MAJOR_TYPE_ARTICLE':
        parts += [opus.get('title'), opus.get('desc')]
    text = '\n'.join(dict.fromkeys(p.strip() for p in parts if isinstance(p, str) and p.strip()))
    if item.get('_full_text'):
        text = item['_full_text']
    pictures = [p.get('url') or p.get('src') for p in opus.get('pics', [])]
    pictures += [p.get('src') for p in (major.get('draw') or {}).get('items', [])]
    return text, [p for p in pictures if isinstance(p, str) and p.startswith('https://')], bool(not item.get('_full_text') and (desc.get('has_more') or summary.get('has_more')))

def opus_text(data, uid, id):
    item = data.get('item') or {}
    if str(item.get('id_str')) != str(id) or str((item.get('basic') or {}).get('uid')) != str(uid):
        raise SourceError('专栏身份与动态不匹配')
    parts = []
    for module in item.get('modules', []):
        if module.get('module_blocked') or module.get('module_paywall'):
            raise SourceError('专栏正文不可访问')
        title = (module.get('module_title') or {}).get('text')
        if title: parts.append(title)
        for paragraph in (module.get('module_content') or {}).get('paragraphs', []):
            text = ''.join((n.get('word') or {}).get('words') or (n.get('rich') or {}).get('text') or '' for n in (paragraph.get('text') or {}).get('nodes', []))
            if text: parts.append(text)
    if len(parts) < 2: raise SourceError('专栏正文不完整')
    return '\n'.join(parts)

def _video(item):
    major = ((item.get('modules') or {}).get('module_dynamic') or {}).get('major') or {}
    return item.get('type') in ('DYNAMIC_TYPE_AV', 'DYNAMIC_TYPE_LIVE_RCMD') or major.get('type') in ('MAJOR_TYPE_ARCHIVE', 'MAJOR_TYPE_VIDEO', 'MAJOR_TYPE_LIVE_RCMD') or bool(item.get('orig') and _video(item['orig']))

def classify_dynamic(item, uid, now):
    author = (item.get('modules') or {}).get('module_author') or {}
    if str(author.get('mid')) != str(uid):
        raise SourceError('动态作者与配置 UID 不匹配')
    id = str(item.get('id_str') or '')
    ts = author.get('pub_ts')
    if isinstance(ts, str) and ts.isdigit(): ts = int(ts)
    if not id.isdigit() or not isinstance(ts, (int, float)) or ts <= 0:
        raise SourceError('动态 ID 或发布时间缺失')
    published = datetime.fromtimestamp(ts, timezone.utc)
    text, images, incomplete = _body(item)
    if item.get('orig'):
        orig_text, orig_images, orig_incomplete = _body(item['orig'])
        text += ('\n转发原文：\n' + orig_text) if orig_text else ''
        images += orig_images
        incomplete = incomplete or orig_incomplete
    from .public_content import content_title
    headline = content_title({'body': text})
    policy_text = re.split(r'[-—_]{8,}', text)[0]
    evidence = []
    for match in DATE.finditer(policy_text):
        y, m, d, h, minute = match.groups()
        try:
            years = [int(y)] if y else [published.astimezone(BJ).year + n for n in (-1, 0, 1)]
            candidates = []
            for year in years:
                try: candidates.append(datetime(year, int(m), int(d), int(h or 0), int(minute or 0), tzinfo=BJ))
                except ValueError: pass
            date = min(candidates, key=lambda t: abs((t - published).total_seconds()))
            evidence.append({'text': match.group(), 'date': date.strftime('%Y-%m-%d' + (' %H:%M' if h else '')), 'year_inferred': not bool(y)})
        except (ValueError, OverflowError):
            continue
    if _video(item): reason = 'video'
    elif re.search(r'抽奖|开奖|中奖|转评赞|一键三连', text): reason = 'lottery'
    elif PROMOTION.search(headline) or (PROMOTION.search(policy_text) and not NOTICE_TITLE.search(headline)): reason = 'promotion'
    elif item.get('type') not in ('DYNAMIC_TYPE_DRAW', 'DYNAMIC_TYPE_WORD', 'DYNAMIC_TYPE_ARTICLE', 'DYNAMIC_TYPE_FORWARD'): reason = 'unsupported'
    elif incomplete: reason = 'incomplete'
    elif not INGAME.search(policy_text): reason = 'not_ingame'
    elif not evidence: reason = 'no_date'
    else: reason = 'accepted'
    return {'id': id, 'source_uid': str(uid), 'source': 'bilibili', 'source_name': 'B站官方动态',
            'author': str(author.get('name') or uid), 'title': (text.splitlines() or ['未命名动态'])[0][:160],
            'body': text, 'summary': text, 'images': images, 'content_type': item.get('type'),
            'content_status': 'video' if _video(item) else 'unavailable' if incomplete else 'full' if text or images else 'unavailable',
            'content_error': '正文补全未成功，下方仅为已读取节选，请查看原文。' if incomplete else '',
            'published_at': published.isoformat(), 'fetched_at': now.isoformat(), 'url': f'https://t.bilibili.com/{id}',
            'decision': 'accepted' if reason == 'accepted' else 'excluded', 'reason': reason,
            'reason_text': REASONS[reason], 'time_evidence': evidence, 'rule_version': RULE_VERSION}

async def collect_pages(fetch, uid, now, *, days=60, mode='backfill', pause=1.5, max_pages=80, on_page=None, on_diagnostic=None):
    cutoff = now - timedelta(days=days)
    window = f'{days}天' + ('增量采集' if mode == 'incremental' else '历史回补')
    retained = f'本轮{window}未完成，已保留已有记录和上次成功状态'
    rows, seen_offsets = {}, set()
    offset = ''
    for page in range(max_pages):
        diagnostic = dict(page=page + 1, item_count=None, has_more=None,
                          cursor_present=False, http_status=None, business_code=None)
        try:
            data = await fetch(offset)
        except SourceError as error:
            diagnostic.update(http_status=error.http_status, business_code=error.business_code)
            if on_diagnostic: on_diagnostic(diagnostic)
            raise SourceError(f'{error}（第{page + 1}页）；{retained}',
                              http_status=error.http_status, business_code=error.business_code) from None
        if isinstance(data, dict):
            more = data.get('has_more')
            diagnostic.update(item_count=len(data['items']) if isinstance(data.get('items'), list) else None,
                              has_more=bool(more) if type(more) in (bool, int) and more in (0, 1) else None,
                              cursor_present=isinstance(data.get('offset'), str) and bool(data['offset']))
        if on_diagnostic: on_diagnostic(diagnostic)
        if not isinstance(data, dict) or not isinstance(data.get('items'), list) or 'has_more' not in data:
            raise SourceError(f'B站第{page + 1}页返回结构异常；{retained}')
        items = data['items']
        if not items:
            location = '首页' if page == 0 else f'第{page + 1}页'
            raise SourceError(f'B站官方动态{location}返回空列表；{retained}')
        dated = []
        page_rows = []
        for item in items:
            row = classify_dynamic(item, uid, now)
            when = datetime.fromisoformat(row['published_at'])
            pinned = ((item.get('modules') or {}).get('module_tag') or {}).get('text') == '置顶'
            if not pinned: dated.append(when)
            if cutoff <= when <= now + timedelta(minutes=5):
                rows[row['id']] = row
                page_rows.append(row)
        if on_page: on_page(page_rows, page + 1)
        if not data['has_more'] or (dated and all(t < cutoff for t in dated)):
            return {'rows': list(rows.values()), 'pages': page + 1, 'complete': True, 'cutoff': cutoff.isoformat()}
        cursor = str(data.get('offset') or '')
        if not cursor or cursor in seen_offsets:
            raise SourceError(f'B站第{page + 1}页分页游标异常；{retained}')
        seen_offsets.add(cursor)
        offset = cursor
        await asyncio.sleep(pause)
    raise SourceError(f'已达到分页上限（{max_pages}页）；{retained}')

class BilibiliClient:
    def __init__(self, uid, credentials=None):
        from bilibili_api import user, Credential, request_settings
        # This domestic source is reachable directly; inheriting the shell's
        # proxy returned 412/empty data during validation. TLS stays verified.
        if request_settings.get_trust_env(): request_settings.set_trust_env(False)
        self.user = user.User(int(uid), credential=Credential(**(credentials or {})))
        self.uid = str(uid)
        self.credential = Credential(**(credentials or {}))

    async def page(self, offset):
        try:
            data = await asyncio.wait_for(self.user.get_dynamics_new(offset=offset), timeout=35)
            from bilibili_api import opus
            for item in data.get('items') or []:
                if not _video(item) and _body(item)[2]:
                    try:
                        detail = await asyncio.wait_for(opus.Opus(int(item['id_str']), credential=self.credential).get_info(), timeout=25)
                        item['_full_text'] = opus_text(detail, self.uid, item['id_str'])
                    except Exception:
                        logger.info("opus 全文补全失败，保留摘要")
            return data
        except Exception as exc:
            # Never log request headers, cookies, or SDK exception text.
            from bilibili_api.exceptions import NetworkException, ResponseCodeException
            error = SourceError('B站请求失败或受到访问限制',
                http_status=exc.status if isinstance(exc, NetworkException) else None,
                business_code=exc.code if isinstance(exc, ResponseCodeException) else None)
            codes = [f'HTTP {error.http_status}'] if error.http_status is not None else []
            if error.business_code is not None: codes.append(f'业务码 {error.business_code}')
            suffix = f'（{", ".join(codes)}）' if codes else ''
            raise SourceError(f'B站请求失败或受到访问限制{suffix}，请稍后重试',
                              http_status=error.http_status, business_code=error.business_code) from None
