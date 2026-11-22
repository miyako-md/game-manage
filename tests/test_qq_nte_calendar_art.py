"""Reviewed NTE calendar crops: manifest bounds, exact matching and cache delivery."""
import asyncio
import hashlib
import json
from datetime import datetime
from io import BytesIO

from PIL import Image
import pytest

from game_assistant.accounts.models import QueryResult
from game_assistant.qq import assets, calendar_art
from game_assistant.qq import render_snapshot as shared
from game_assistant.qq.calendar_art import CalendarArt, Source, Tile, crop_tiles, crop_url, load_manifest

NOW = datetime.fromisoformat('2026-11-22T12:00:00+08:00')
SOURCE_URL = 'https://bbs-upload.tajiduo.com/20261103/10100006/calendar.jpeg'


def jpeg(size=(200, 100)):
    output = BytesIO()
    Image.new('RGB', size, '#3355aa').save(output, 'JPEG')
    return output.getvalue()


RAW = jpeg()


def source(raw=RAW, tiles=None, version='1.5'):
    tiles = tiles or (Tile('t01', '甲活动', '2026-11-05', '2026-11-26', (100, 10, 80, 40)),
                      Tile('t02', '乙活动', None, None, (10, 60, 60, 30)))
    return Source('nte', version, '529916', SOURCE_URL, hashlib.sha256(raw).hexdigest(), len(raw), 200, 100, tuple(tiles))


@pytest.fixture
def art(monkeypatch):
    value = CalendarArt([source()])
    monkeypatch.setattr(calendar_art, 'CALENDAR_ART', value)
    monkeypatch.setattr(assets, 'CALENDAR_ART', value)
    return value


def manifest(tmp_path, **changes):
    raw = {'game': 'nte', 'version': '1.5', 'post_id': '529916', 'image_url': SOURCE_URL,
           'sha256': 'a' * 64, 'bytes': 10, 'width': 200, 'height': 100,
           'tiles': [{'id': 't01', 'name': '甲活动', 'start_date': '2026-11-05', 'end_date': '2026-11-26', 'box': [100, 10, 80, 40]}]}
    raw.update(changes)
    path = tmp_path / 'art.json'
    path.write_text(json.dumps({'schema': 1, 'sources': [raw]}, ensure_ascii=False), encoding='utf-8')
    return path


def test_packaged_manifest_is_valid_and_every_crop_url_is_safe():
    sources = load_manifest()
    assert sources and all(s.game == 'nte' for s in sources)
    for item in sources:
        assert assets.safe_public_url(item.image_url) == item.image_url
        for tile in item.tiles:
            x, y, w, h = tile.box
            assert x + w <= item.width and y + h <= item.height
            assert assets.safe_public_url(crop_url(item, tile)) == crop_url(item, tile)


@pytest.mark.parametrize('changes', [
    {'tiles': [{'id': 't01', 'name': '甲', 'start_date': None, 'end_date': None, 'box': [150, 10, 80, 40]}]},
    {'tiles': [{'id': 't01', 'name': '甲', 'start_date': '2026-11-31', 'end_date': None, 'box': [0, 0, 20, 20]}]},
    {'tiles': [{'id': 'x1', 'name': '甲', 'start_date': None, 'end_date': None, 'box': [0, 0, 20, 20]}]},
    {'tiles': [{'id': 't01', 'name': '甲', 'start_date': None, 'end_date': None, 'box': [0, 0, 5, 20]}]},
    {'image_url': 'https://bbs-upload.tajiduo.com/a.jpeg?token=1'},
    {'sha256': 'not-a-digest'},
    {'bytes': 7 * 1024 * 1024},
    {'width': 5000, 'height': 5000},
    {'game': 'wuthering_waves'},
])
def test_one_malformed_entry_disables_the_whole_manifest(tmp_path, changes):
    assert len(load_manifest(manifest(tmp_path))) == 1
    assert load_manifest(manifest(tmp_path, **changes)) == ()


def test_missing_manifest_gives_no_crops(tmp_path):
    assert load_manifest(tmp_path / 'absent.json') == ()


@pytest.mark.parametrize('event,expected', [
    ({'name': '甲活动', 'version': '1.5', 'start_date': '2026-11-05', 'end_date': '2026-11-26'}, 't01'),
    # An instant is compared on its Beijing calendar day.
    ({'name': '甲活动', 'version': '1.5', 'start_at': '2026-11-04T21:00:00+00:00', 'end_at': '2026-11-26T05:59:00+08:00'}, 't01'),
    ({'name': '甲活动', 'version': '1.5', 'end_date': '2026-11-26'}, 't01'),
    ({'name': '甲活动', 'version': '1.5', 'start_date': '2026-11-05', 'end_date': '2026-11-27'}, None),
    ({'name': '甲活动', 'version': '1.5'}, None),
    ({'name': '甲活动', 'version': '1.6', 'start_date': '2026-11-05', 'end_date': '2026-11-26'}, None),
    ({'name': '甲活动·攻坚', 'version': '1.5', 'start_date': '2026-11-05', 'end_date': '2026-11-26'}, None),
    ({'name': '乙活动', 'version': '1.5'}, 't02'),
    ({'name': '乙活动'}, None),
])
def test_event_matches_only_exact_reviewed_name_version_and_dates(art, event, expected):
    found = art.match_event(event, 'nte')
    assert found == (crop_url(art.sources[0], next(t for t in art.sources[0].tiles if t.id == expected)) if expected else None)
    assert art.match_event(event, 'wuthering_waves') is None


def test_two_reviewed_tiles_for_one_event_give_no_crop():
    tiles = (Tile('t01', '甲活动', None, '2026-11-26', (0, 0, 20, 20)), Tile('t02', '甲活动', None, '2026-11-26', (20, 0, 20, 20)))
    assert CalendarArt([source(tiles=tiles)]).match_event({'name': '甲活动', 'version': '1.5', 'end_date': '2026-11-26'}, 'nte') is None


def test_only_listed_crop_urls_are_safe(art):
    listed = crop_url(art.sources[0], art.sources[0].tiles[0])
    assert assets.safe_public_url(listed) == listed
    for value in (listed.replace('t01', 't09'), listed + '?a=1', listed.replace('https', 'http'),
                  listed.replace('.png', '.jpg'), listed.upper()):
        assert assets.safe_public_url(value) is None


async def test_crop_host_is_never_downloaded(art):
    with pytest.raises(ValueError, match='qq_asset_crop_unknown'):
        await assets._download(crop_url(art.sources[0], art.sources[0].tiles[0]))


def test_crops_require_the_reviewed_source_bytes_and_size():
    item = source()
    crops = crop_tiles(RAW, item)
    assert list(crops) == [crop_url(item, t) for t in item.tiles]
    with Image.open(BytesIO(crops[crop_url(item, item.tiles[0])])) as image:
        assert image.size == (80, 40)
    with pytest.raises(ValueError, match='crop_source_mismatch'):
        crop_tiles(RAW + b'x', item)
    other = jpeg((201, 100))
    with pytest.raises(ValueError, match='crop_source_mismatch'):
        crop_tiles(other, source(raw=other))


async def test_reply_defers_the_source_then_one_download_fills_every_crop(art, monkeypatch, tmp_path):
    calls = []
    async def download(url, **kwargs):
        calls.append((url, kwargs.get('timeout_cap'), kwargs.get('artwork')))
        return RAW
    monkeypatch.setattr(assets, '_download', download)
    cache = assets.PublicAssetCache(disk_directory=tmp_path)
    first, second = (crop_url(art.sources[0], t) for t in art.sources[0].tiles)
    ref = cache.register_url(first, artwork=True)
    stats = await cache.prefetch([ref], budget_seconds=1)
    # The reply never waits for the large source; the background refetch does.
    assert stats['timeout'] == 1 and cache.get_png(ref) is None
    for _ in range(50):
        if cache.get_png(ref) is not None:
            break
        await asyncio.sleep(.01)
    assert calls == [(SOURCE_URL, assets.CROP_SOURCE_TIMEOUT, True)]
    with Image.open(BytesIO(cache.get_url_png(first, artwork=True))) as image:
        assert image.size == (80, 40)
    # The crop nobody asked for went to the disk tier, not the memory LRU.
    other = 'qqasset_' + hashlib.sha256(('artwork-v1:' + second).encode('ascii')).hexdigest()
    assert other not in cache._cache and cache.get_url_png(second, artwork=True) is not None
    assert await cache.prefetch([cache.register_url(second, artwork=True)], budget_seconds=1) == {'hit': 1, 'miss': 0, 'failed': 0, 'timeout': 0}
    assert len(calls) == 1
    await cache.aclose()


async def test_mismatched_source_is_remembered_as_a_deterministic_failure(art, monkeypatch):
    async def download(url, **kwargs):
        return RAW + b'changed'
    monkeypatch.setattr(assets, '_download', download)
    cache = assets.PublicAssetCache()
    ref = cache.register_url(crop_url(art.sources[0], art.sources[0].tiles[0]), artwork=True)
    await cache.prefetch([ref], budget_seconds=1)
    for _ in range(50):
        if ref in cache._failures:
            break
        await asyncio.sleep(.01)
    assert cache.get_png(ref) is None and ref in cache._failures
    await cache.aclose()


def test_reviewed_crop_leads_nte_calendar_artwork_only(art):
    shared_art = 'https://bbs-upload.tajiduo.com/version.jpg'
    events = [{'name': '甲活动', 'version': '1.5', 'start_date': '2026-11-05', 'end_date': '2026-11-26', 'image_urls': [shared_art]},
              {'name': '丙活动', 'version': '1.5', 'image_urls': [shared_art]}]
    row = QueryResult(events, NOW.isoformat(), 'ok', True)
    empty = QueryResult([], NOW.isoformat(), 'ok', True)
    crop = crop_url(art.sources[0], art.sources[0].tiles[0])
    nte = shared.calendar_snapshot({'nte': shared.events_with_artwork(row, empty, 'nte')}, NOW)
    payload = nte['display_data']['snapshots']['nte']['events']['payload']
    assert payload[0]['image_urls'] == [crop, shared_art] and payload[1]['image_urls'] == [shared_art]
    assert (crop, 'artwork') in set(shared.asset_requests(nte))
    other = shared.events_with_artwork(row, empty, 'wuthering_waves')
    assert other.payload[0]['image_urls'] == [shared_art]
