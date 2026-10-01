"""Read a guide's actual content, extract evidence and persist per-form advice."""
import asyncio
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import urlsplit

import httpx

from .nte_guides import TextBlocks
from .nte_ocr import IMAGE_URL_RE
from .wuwa_guide_updates import HEADERS, MAX_BYTES, parse_candidate, plain
from .wuwa_reviewed_guides import REVIEWED

POST_URL = 'https://api.kurobbs.com/forum/getPostDetail'
SECTION_KEYS = ('weapons', 'teams', 'echo_sets', 'echo_stats', 'skill_priority')
MAX_IMAGES = 10
IMAGE_BYTES = 8 * 1024 * 1024
RULE_VERSION = 1
PATTERNS = {
    'weapons': re.compile(r'武器|专武'),
    'teams': re.compile(r'配队|队友|队伍|奶妈'),
    'echo_sets': re.compile(r'(?:声骸|合鸣|套装).*(?:件|首位|套)|(?:套装|首位).*(?:推荐|选择)'),
    'echo_stats': re.compile(r'COST\s*[134]|主词条|副词条|副属性', re.I),
    'skill_priority': re.compile(r'技能(?:升级|加点|优先)|升级(?:顺序|优先)'),
}


class SourceError(Exception):
    pass


def safe_image(value):
    if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 33 for c in value):
        return None
    try:
        url = urlsplit(value)
        if (url.scheme == 'https' and url.hostname in (
                'prod-alicdn-community.kurobbs.com', 'prod-tencent-cos-community.kurobbs.com',
                'web-static.kurobbs.com') and not url.username and not url.password
                and url.port in (None, 443) and not url.fragment
                and re.search(r'\.(?:png|jpe?g|webp)$', url.path, re.I)):
            return value
    except ValueError:
        pass
    return None


def parse_source(raw, post_id, query):
    data = raw.get('data') if isinstance(raw, dict) and raw.get('code') == 200 else None
    detail = data.get('postDetail') if isinstance(data, dict) else None
    if (not isinstance(detail, dict) or str(detail.get('id', detail.get('postId'))) != post_id
            or detail.get('isHide') or detail.get('isDown') or detail.get('isDelete')):
        raise SourceError('原帖已不可用或身份不匹配')
    candidate = parse_candidate({**detail, 'postId': post_id, 'userId': detail.get('postUserId')}, query)
    if not candidate or candidate['kind'] == 'video':
        raise SourceError('原帖不是当前角色的图文培养攻略')
    paragraphs, images = [], []
    blocks = detail.get('postContent')
    if isinstance(blocks, list) and blocks:
        if len(blocks) > 300 or any(not isinstance(block, dict) for block in blocks):
            raise SourceError('原帖正文格式异常')
        for block in blocks:
            if block.get('contentType') == 2:
                images.append({'page': len(images) + 1, 'url': safe_image(block.get('url'))})
            elif block.get('contentType') == 1:
                text = plain(block.get('content')).strip()
                if text and not re.search(r'UID|账号|关注|点赞|转发', text, re.I):
                    paragraphs.append({'position':len(paragraphs) + 1, 'text':text.lstrip('🌙 ').strip()})
    else:
        html = detail.get('postH5Content')
        if not isinstance(html, str) or not html.strip() or len(html) > 200000:
            raise SourceError('原帖正文为空或不完整')
        parser = TextBlocks(); parser.feed(html)
        for line in ''.join(parser.parts).splitlines():
            text = line.strip()
            if text and not re.search(r'UID|账号|关注|点赞|转发', text, re.I):
                paragraphs.append({'position':len(paragraphs) + 1, 'text':text})
        images = [{'page':i, 'url':safe_image(m.group(1))} for i,m in enumerate(IMAGE_URL_RE.finditer(html),1)]
    if sum(len(p['text']) for p in paragraphs) > 200000 or len(images) > 40 or not (paragraphs or images):
        raise SourceError('原帖正文为空或过大')
    return {**candidate, 'paragraphs':paragraphs, 'images':images}


def source_fingerprint(source, hashes):
    value = {'title':source['title'], 'author_id':source['author_id'],
             'paragraphs':source['paragraphs'], 'images':source['images'], 'hashes':hashes}
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def extract_sections(source, pages, ocr_error):
    """Keep explicit prose and OCR evidence; never infer ordering from icon positions."""
    result = []
    for key in SECTION_KEYS:
        selected = [p for p in source['paragraphs'] if PATTERNS[key].search(p['text'])][:2]
        evidence = [{'kind':'text', 'position':p['position']} for p in selected]
        text = '\n'.join(p['text'] for p in selected)
        # Pictures can provide missing facts or upgrade order absent from the prose.
        # Skill icons may be sorted wrongly by OCR, so preserve labels as an excerpt.
        for page in pages:
            lines = sorted([line for line in page['lines'] if line['confidence'] >= .85],
                           key=lambda line:(min(p[1] for p in line['box']), min(p[0] for p in line['box'])))
            headings = [i for i,line in enumerate(lines) if PATTERNS[key].search(line['text'])]
            if not headings or (text and key != 'skill_priority'):
                continue
            start = headings[0]
            stop = min(start + 16, len(lines))
            block = lines[start:stop]
            # No ranking operators are generated; source text and location remain visible.
            excerpt = '；'.join(line['text'] for line in block
                               if not re.search(r'UID|关注|点赞|Page\s*\d|图文',line['text'],re.I))
            if excerpt:
                if not text:
                    text = '原图识别片段：' + excerpt[:600]
                evidence.append({'kind':'image','page':page['page'],
                                 'boxes':[line['box'] for line in block]})
                break
        note = '自动提炼，待核对原帖；适用条件按来源保留。'
        if key == 'skill_priority' and any(e['kind'] == 'image' for e in evidence):
            note += '图标之间的优先级关系未确认，不将识别位置当作加点顺序。'
        if not text:
            note = '原帖尚未识别到明确建议，保留缺项。'
            if ocr_error: note += ocr_error
        result.append({'key':key, 'text':text, 'status':'extracted' if text else 'pending',
                       'sourceId':source['id'], 'locator':'、'.join(
                           f"正文第 {e['position']} 段" if e['kind']=='text' else f"原帖第 {e['page']} 张图" for e in evidence),
                       'note':note, 'evidence':evidence})
    return result


def recognize(images):
    from .nte_ocr import load_ocr_engine, OcrUnavailableError
    try:
        import cv2
        import numpy as np
        from PIL import Image
        import io
        engine = load_ocr_engine()
    except (ImportError, OcrUnavailableError):
        return [], '图文识别组件未安装，可安装项目的 ocr 可选依赖。'
    except Exception:
        return [], '图文识别组件暂时不可用，保留明确正文。'
    pages, errors = [], []
    for page, blob in images:
        try:
            with Image.open(io.BytesIO(blob)) as meta:
                if meta.width * meta.height > 12_000_000 or max(meta.size) > 16000:
                    raise ValueError('image dimensions exceed limit')
            pixels = cv2.imdecode(np.frombuffer(blob, np.uint8), cv2.IMREAD_COLOR)
            if pixels is None: raise ValueError('bad image')
            raw = engine(pixels)[0] or []
            lines = [{'text':str(text), 'confidence':float(score),
                      'box':[[float(x),float(y)] for x,y in box]} for box,text,score in raw]
            pages.append({'page':page, 'lines':lines})
        except Exception:
            errors.append(page)
    return pages, '部分配图识别失败，保留明确正文。' if errors else None


class GuideExtractor:
    def __init__(self, path, reviewed=None):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
        self.reviewed = REVIEWED if reviewed is None else reviewed
        self.lock, self.attempts = asyncio.Lock(), {}
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS guide_active (key TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            conn.commit()

    def active(self, query):
        with closing(sqlite3.connect(self.path)) as conn:
            row = conn.execute('SELECT payload FROM guide_active WHERE key=?', (query.key,)).fetchone()
        if row:
            try:
                value = json.loads(row[0])
                if isinstance(value,dict) and isinstance(value.get('guide'),dict): return value
            except ValueError:
                pass
        return {'guide':None, 'error':None}

    def save(self, query, value):
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute('INSERT INTO guide_active VALUES (?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload',
                         (query.key,json.dumps(value,ensure_ascii=False)))
            conn.commit()

    async def extract(self, query, post_id, force=False):
        async with self.lock:
            previous = self.active(query)
            last = previous.get('guide')
            attempt_key = (query.key,post_id)
            if time.monotonic() - self.attempts.get(attempt_key,-1000) < 30:
                return {**previous,'deferred':True}
            if (not force and last and last.get('sourceId')==post_id and last.get('ruleVersion')==RULE_VERSION
                    and not previous.get('error') and time.time()-datetime.fromisoformat(last['fetchedAt']).timestamp()<86400):
                return previous
            self.attempts[attempt_key] = time.monotonic()
            try:
                async with asyncio.timeout(90), httpx.AsyncClient(timeout=15, headers=HEADERS, follow_redirects=False) as client:
                    blob = await self.read_bytes(client,'POST',POST_URL,MAX_BYTES,data={'postId':post_id})
                    source = parse_source(json.loads(blob),post_id,query)
                    hashes, images, missing = [], [], False
                    for image in source['images'][:MAX_IMAGES]:
                        try:
                            if not image['url']: raise SourceError('unsafe image')
                            blob = await self.read_bytes(client,'GET',image['url'],IMAGE_BYTES)
                            hashes.append(hashlib.sha256(blob).hexdigest())
                            images.append((image['page'],blob))
                        except (httpx.HTTPError, SourceError):
                            hashes.append(None); missing = True
                    fingerprint = source_fingerprint(source,hashes)
                    reviewed = self.reviewed.get(post_id)
                    verified = bool(reviewed and reviewed['character_id']==query.character_id
                                    and reviewed['fingerprint']==fingerprint and not missing)
                    if verified:
                        pages, ocr_error = [], None
                        summaries = {s['key']:s for s in reviewed['sections']}
                        sections = extract_sections(source,[],None)
                        for section in sections:
                            if section['key'] in summaries:
                                section.update(deepcopy(summaries[section['key']]),status='reviewed')
                    else:
                        pages, ocr_error = await asyncio.to_thread(recognize,images) if images else ([],None)
                        sections = extract_sections(source,pages,ocr_error)
                    source_meta = {k:source[k] for k in ('id','title','author','version','url','kind')}
                    source_meta.update(publishedAt=source['published_at'])
                    guide = {'id':query.character_id,'name':query.name,'attribute':query.attribute,
                             'sections':sections,'sources':[source_meta], 'sourceId':post_id,
                             'fetchedAt':datetime.now(timezone.utc).isoformat(),
                             'reviewedAt':reviewed['reviewedAt'] if verified else None,
                             'fingerprint':fingerprint,'ruleVersion':RULE_VERSION,
                             'images':source['images'][:MAX_IMAGES],
                             'extractionNote':ocr_error or ('部分配图未读取，提炼可能不完整。' if missing or len(source['images'])>MAX_IMAGES else None)}
                    value = {'guide':guide,'error':None}
            except (httpx.HTTPError, SourceError, ValueError, TypeError, TimeoutError):
                value = {**previous,'error':'原帖提炼失败，保留上次培养建议，请稍后重试。'}
            self.save(query,value)
            return value

    @staticmethod
    async def read_bytes(client,method,url,limit,**kwargs):
        body = bytearray()
        async with client.stream(method,url,**kwargs) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body)>limit: raise SourceError('source body too large')
        return bytes(body)
