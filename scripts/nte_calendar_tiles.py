"""异环版本「活动日历」长图 → QQ 日历横幅裁切清单草稿（本机离线工具）。

每个版本运行一次，人工核对后把结果写进
src/game_assistant/qq/nte_calendar_art.json。线上服务只按清单里的坐标裁切，
不做识别；本工具需要可选依赖 `.[ocr]`（RapidOCR、OpenCV），不随线上安装。

用法（仓库根目录）：
  python scripts/nte_calendar_tiles.py --post-id 529916 --out nte-calendar-review

输出目录里有：
  manifest-draft.json  清单草稿（结构与 nte_calendar_art.json 的 sources[] 一项相同）
  review.txt           每个格子的 OCR 文本、匹配到的活动、需要人工确认的原因
  tiles/*.png          每个格子按 box 裁出的预览图（人工确认画面没有切到文字或别的格子）

只读公开接口：塔吉多匿名帖子详情、帖子原图、匿名活动列表；不使用任何账号凭据。
"""
import argparse
import asyncio
import difflib
import hashlib
import json
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

OFFICIAL_UID = '10100006'
BEIJING = timezone(timedelta(hours=8))
TILE_DATES = re.compile(r'(?<!\d)(\d{1,2})\.(\d{2})\s*[-–~]\s*(\d{1,2})\.(\d{2})(?!\d)')
# Pool tiles carry no dates; their category names the pool kind instead.
POOL_HINTS = {'角色卡池': '限定棋盘', '弧盘研募': '特刊'}
ART_LEFT = 0.42   # fallback start of the artwork when no left-side text was read
TEXT_START = 0.35 # name/date lines start in this left part; badges on the right are ignored
INSET = 6         # keep clear of the tile's light border


def norm(value):
    return re.sub(r'[\s·・「」『』<>〈〉《》]', '', unicodedata.normalize('NFKC', str(value or '')))


def detect_tiles(image):
    import cv2
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    height, width = image.shape[:2]
    boxes = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        # Light-bordered wide tiles right of the category rail.
        if w > 150 and 60 < h < 260 and w / h > 2.2 and x > width * 0.1:
            if not any(abs(x - a) < 12 and abs(y - b) < 12 and abs(w - c) < 24 and abs(h - d) < 24 for a, b, c, d in boxes):
                boxes.append((x, y, w, h))
    # A tile containing two others (the seven-day strip) is a row, not an activity.
    def contains(outer, inner):
        return outer != inner and outer[0] <= inner[0] and outer[1] <= inner[1] and \
            outer[0] + outer[2] >= inner[0] + inner[2] and outer[1] + outer[3] >= inner[1] + inner[3]
    boxes = [b for b in boxes if sum(contains(b, other) for other in boxes) < 2]
    return sorted(boxes, key=lambda b: (b[1], b[0]))


def tile_dates(text, year):
    match = TILE_DATES.search(text)
    if not match:
        return None, None
    m1, d1, m2, d2 = map(int, match.groups())
    start = datetime(year, m1, d1)
    end = datetime(year + (1 if m2 < m1 else 0), m2, d2)
    return start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')


def art_box(box, width, height, lines=()):
    """Right of the printed name/date: OCR boxes of lines starting in the left part."""
    x, y, w, h = box
    edges = [max(p[0] for p in line[0]) for line in lines or []
             if line and min(p[0] for p in line[0]) < w * TEXT_START]
    offset = int(max(edges) + INSET) if edges else int(w * ART_LEFT)
    offset = max(int(w * 0.3), min(offset, w - INSET - 32))
    left = x + offset
    return [left, y + INSET, min(width, x + w - INSET) - left, h - 2 * INSET]


def match(event, tiles):
    """Return (tile, reason) candidates for one event; dates must agree when both exist."""
    name = norm(event['name'])
    start = event.get('start_date') or (event.get('start_at') or '')[:10] or None
    end = event.get('end_date') or (event.get('end_at') or '')[:10] or None
    found = []
    for tile in tiles:
        text = norm(tile['ocr_text'])
        exact = name and name in text
        ratio = max((difflib.SequenceMatcher(None, name, text[i:i + len(name)]).ratio()
                     for i in range(max(1, len(text) - len(name) + 1))), default=0)
        if not exact and ratio < 0.75:
            continue
        if tile['start_date'] and start and tile['start_date'] != start:
            continue
        if tile['end_date'] and end and tile['end_date'] != end:
            continue
        hint = POOL_HINTS.get(event.get('category'))
        if hint and hint not in tile['ocr_text']:
            continue
        if not hint and '限定棋盘' in tile['ocr_text']:
            continue
        found.append((tile, 'exact' if exact else f'fuzzy {ratio:.2f}'))
    return found


async def load_events(path):
    if path:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    from fastapi.encoders import jsonable_encoder
    from game_assistant.config import Settings
    from game_assistant.adapters.neverness.adapter import NteAdapter
    settings = Settings()
    settings.nte_access_token = settings.nte_refresh_token = ''
    settings.nte_events = []
    result = await NteAdapter(settings).fetch_events()
    if not result.ok:
        raise SystemExit(f'活动列表读取失败：{result.error}')
    return jsonable_encoder(result.payload)


async def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--post-id', required=True)
    parser.add_argument('--out', default='nte-calendar-review')
    parser.add_argument('--version', help='版本号，例如 1.5；默认从帖子标题读取')
    parser.add_argument('--events-json', help='改用本地活动 JSON（数组，含 name/category/start_date/end_date）')
    args = parser.parse_args(argv)
    import cv2
    import httpx
    import numpy
    from game_assistant.nte_ocr import load_ocr_engine
    from game_assistant.adapters.neverness.endpoints import GET_POST_FULL
    from game_assistant.adapters.neverness.tajiduo_client import TajiduoWebClient
    from game_assistant.qq.assets import ALLOWED_HOSTS

    async with TajiduoWebClient() as web:
        post = await web.get_post_full(args.post_id)
    subject = str(post.get('subject') or '')
    if str(post.get('uid')) != OFFICIAL_UID or '活动日历' not in subject:
        raise SystemExit(f'不是官方活动日历帖：uid={post.get("uid")} 标题={subject}')
    version = args.version or (re.search(r'(\d+\.\d+)\s*版本', subject) or [None, None])[1]
    if not version:
        raise SystemExit('标题里没有版本号，请用 --version 指定')
    images = [i for i in post.get('images') or [] if isinstance(i, dict)]
    if len(images) != 1:
        raise SystemExit(f'帖子应只有 1 张日历图，实际 {len(images)} 张')
    url = images[0]['url']
    if httpx.URL(url).host not in ALLOWED_HOSTS or not url.startswith('https://'):
        raise SystemExit(f'图片不在 QQ 白名单图床：{url}')
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=60) as client:
        response = await client.get(url)
        response.raise_for_status()
        raw = response.content
    image = cv2.imdecode(numpy.frombuffer(raw, numpy.uint8), cv2.IMREAD_COLOR)
    height, width = image.shape[:2]
    published = datetime.fromtimestamp(int(post['createTime']) / 1000, BEIJING)

    ocr = load_ocr_engine()
    tiles = []
    for index, box in enumerate(detect_tiles(image), 1):
        x, y, w, h = box
        lines, _ = ocr(image[y:y + h, x:x + w])
        text = ' '.join(line[1] for line in lines or [])
        start, end = tile_dates(text, published.year)
        tiles.append({'id': f't{index:02d}', 'tile': list(box), 'box': art_box(box, width, height, lines),
                      'ocr_text': text, 'start_date': start, 'end_date': end})

    events = await load_events(args.events_json)
    chosen, review = {}, []
    for event in events:
        if str(event.get('version') or version) != version:
            continue
        found = match(event, tiles)
        if len(found) == 1:
            tile, reason = found[0]
            if tile['id'] in chosen:
                review.append(f'格子 {tile["id"]} 同时匹配「{chosen[tile["id"]]["name"]}」和「{event["name"]}」，均未采用')
                chosen.pop(tile['id'])
                continue
            start = event.get('start_date') or (event.get('start_at') or '')[:10] or None
            end = event.get('end_date') or (event.get('end_at') or '')[:10] or None
            chosen[tile['id']] = {'id': tile['id'], 'name': event['name'], 'start_date': start,
                                  'end_date': end, 'box': tile['box']}
            if reason != 'exact':
                review.append(f'「{event["name"]}」按近似文字匹配 {tile["id"]}（{reason}），请看预览图确认')
        elif found:
            review.append(f'「{event["name"]}」匹配到多个格子 {[t["id"] for t, _ in found]}，均未采用')
        else:
            review.append(f'「{event["name"]}」在日历图里没有对应格子')

    out = Path(args.out)
    (out / 'tiles').mkdir(parents=True, exist_ok=True)
    for tile in tiles:
        left, top, w, h = tile['box']
        name = chosen.get(tile['id'], {}).get('name', '未匹配')
        cv2.imencode('.png', image[top:top + h, left:left + w])[1].tofile(str(out / 'tiles' / f'{tile["id"]}-{name}.png'))
    source = {'game': 'nte', 'version': version, 'post_id': str(args.post_id),
              'post_url': f'https://www.tajiduo.com/bbs/index.html#/post?postId={args.post_id}',
              'image_url': url, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
              'width': width, 'height': height,
              'tiles': sorted(chosen.values(), key=lambda t: t['id'])}
    (out / 'manifest-draft.json').write_text(json.dumps(source, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    lines = [f'{subject}  {GET_POST_FULL}?postId={args.post_id}', f'图片 {width}x{height} {len(raw)} 字节', '']
    for tile in tiles:
        hit = chosen.get(tile['id'])
        lines.append(f'{tile["id"]} {tile["tile"]} {tile["start_date"]}~{tile["end_date"]} '
                     f'→ {hit["name"] if hit else "（未匹配）"} | {tile["ocr_text"]}')
    lines += ['', '需要人工确认：', *(review or ['无'])]
    (out / 'review.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines))
    print(f'\n已写入 {out.resolve()}')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    asyncio.run(main())
