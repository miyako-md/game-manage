"""Reviewed banner crops from official NTE version activity calendars.

The manifest (nte_calendar_art.json) is produced offline by
scripts/nte_calendar_tiles.py and checked by a person. At runtime nothing is
recognised or guessed: an event receives a crop only when its version, exact
name and dates equal one reviewed tile, and the crop is cut with Pillow at the
reviewed box from source bytes whose sha256 equals the reviewed digest.

A crop is addressed by a virtual URL on a host that never resolves
(``.invalid``). Such a URL is safe only when it is listed in the manifest; the
asset cache serves it from its own cropped PNG and never sends it to the network.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
from io import BytesIO
import json
import logging
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlsplit
import warnings

from PIL import Image

logger = logging.getLogger(__name__)

CROP_HOST = 'nte-calendar-art.invalid'
MANIFEST_PATH = Path(__file__).with_name('nte_calendar_art.json')
BEIJING = timezone(timedelta(hours=8))
MAX_SOURCES = 16
MAX_TILES = 64
# Same bounds the asset cache applies to any artwork download.
MAX_SOURCE_BYTES = 6 * 1024 * 1024
MAX_SOURCE_PIXELS = 12_000_000
MIN_TILE_EDGE = 16


@dataclass(frozen=True)
class Tile:
    id: str
    name: str
    start_date: str | None
    end_date: str | None
    box: tuple[int, int, int, int]


@dataclass(frozen=True)
class Source:
    game: str
    version: str
    post_id: str
    image_url: str
    sha256: str
    bytes: int
    width: int
    height: int
    tiles: tuple[Tile, ...]


def _day(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return None
    try:
        date.fromisoformat(value)
    except ValueError:
        return None
    return value


def _int(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('calendar_art_manifest_invalid')
    return value


def _source(raw):
    if not isinstance(raw, dict) or raw.get('game') != 'nte':
        raise ValueError('calendar_art_manifest_invalid')
    version, post_id, url, digest = (raw.get(key) for key in ('version', 'post_id', 'image_url', 'sha256'))
    parts = urlsplit(url) if isinstance(url, str) else None
    if (not isinstance(version, str) or not re.fullmatch(r'\d+\.\d+', version)
            or not isinstance(post_id, str) or not re.fullmatch(r'\d{1,20}', post_id)
            or not parts or parts.scheme != 'https' or parts.query or parts.fragment or parts.username
            or not re.fullmatch(r'/[A-Za-z0-9/_.-]+\.(?:png|jpe?g|webp)', parts.path, re.I)
            or not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest)):
        raise ValueError('calendar_art_manifest_invalid')
    width, height = _int(raw.get('width'), 1, 20000), _int(raw.get('height'), 1, 20000)
    if width * height > MAX_SOURCE_PIXELS:
        raise ValueError('calendar_art_manifest_invalid')
    tiles, ids = [], set()
    entries = raw.get('tiles')
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_TILES:
        raise ValueError('calendar_art_manifest_invalid')
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError('calendar_art_manifest_invalid')
        tile_id, name, box = entry.get('id'), entry.get('name'), entry.get('box')
        start, end = entry.get('start_date'), entry.get('end_date')
        if (not isinstance(tile_id, str) or not re.fullmatch(r't\d{2}', tile_id) or tile_id in ids
                or not isinstance(name, str) or not 1 <= len(name.strip()) <= 40
                or (start is not None and not _day(start)) or (end is not None and not _day(end))
                or (start and end and start > end)
                or not isinstance(box, list) or len(box) != 4):
            raise ValueError('calendar_art_manifest_invalid')
        x, y = _int(box[0], 0, width - 1), _int(box[1], 0, height - 1)
        w, h = _int(box[2], MIN_TILE_EDGE, width), _int(box[3], MIN_TILE_EDGE, height)
        if x + w > width or y + h > height:
            raise ValueError('calendar_art_manifest_invalid')
        ids.add(tile_id)
        tiles.append(Tile(tile_id, name.strip(), start, end, (x, y, w, h)))
    return Source('nte', version, post_id, url, digest, _int(raw.get('bytes'), 1, MAX_SOURCE_BYTES),
                  width, height, tuple(tiles))


def load_manifest(path=MANIFEST_PATH):
    """All reviewed sources, or none: one malformed entry disables the manifest."""
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(data, dict) or data.get('schema') != 1 or not isinstance(data.get('sources'), list) \
                or len(data['sources']) > MAX_SOURCES:
            raise ValueError('calendar_art_manifest_invalid')
        sources = tuple(_source(raw) for raw in data['sources'])
        if len({s.sha256 for s in sources}) != len(sources):
            raise ValueError('calendar_art_manifest_invalid')
        return sources
    except FileNotFoundError:
        return ()
    except (OSError, ValueError, TypeError):
        logger.warning('calendar_art_manifest_invalid')
        return ()


def crop_url(source, tile):
    return f'https://{CROP_HOST}/{source.sha256[:16]}/{tile.id}.png'


class CalendarArt:
    def __init__(self, sources=None):
        self.sources = load_manifest() if sources is None else tuple(sources)
        self._index = {crop_url(s, t): (s, t) for s in self.sources for t in s.tiles}

    def lookup(self, url):
        return self._index.get(url)

    def urls(self, source):
        return [crop_url(source, tile) for tile in source.tiles]

    def match_event(self, event, game):
        """The one reviewed crop for this event, else None (ambiguity gives nothing)."""
        if game != 'nte' or not isinstance(event, dict):
            return None
        name = _name(event.get('name'))
        version = str(event.get('version_id') or event.get('version') or '')
        if not name or not version:
            return None
        start = _event_day(event, 'start')
        end = _event_day(event, 'end')
        hits = []
        for source in self.sources:
            if source.version != version:
                continue
            for tile in source.tiles:
                if _name(tile.name) != name:
                    continue
                compared = [(a, b) for a, b in ((tile.start_date, start), (tile.end_date, end)) if a and b]
                if any(a != b for a, b in compared):
                    continue
                if (tile.start_date or tile.end_date) and not compared:
                    continue
                hits.append(crop_url(source, tile))
        return hits[0] if len(hits) == 1 else None


def _name(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', value)) if isinstance(value, str) else ''


def _event_day(event, side):
    day = _day(event.get(f'{side}_date'))
    if day:
        return day
    value = event.get(f'{side}_at')
    if not isinstance(value, str):
        return None
    try:
        instant = datetime.fromisoformat(value)
    except ValueError:
        return None
    if instant.tzinfo is None:
        return None
    return instant.astimezone(BEIJING).date().isoformat()


def crop_tiles(raw, source):
    """Reviewed crops as lossless PNG bytes keyed by crop URL; mismatched source raises."""
    if not isinstance(raw, bytes) or len(raw) != source.bytes or hashlib.sha256(raw).hexdigest() != source.sha256:
        raise ValueError('qq_asset_crop_source_mismatch')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw), formats=('JPEG', 'PNG', 'WEBP')) as image:
                if image.size != (source.width, source.height) or getattr(image, 'n_frames', 1) != 1:
                    raise ValueError('qq_asset_crop_source_mismatch')
                image.load()
                result = {}
                for tile in source.tiles:
                    x, y, w, h = tile.box
                    output = BytesIO()
                    image.crop((x, y, x + w, y + h)).convert('RGB').save(output, 'PNG')
                    result[crop_url(source, tile)] = output.getvalue()
                return result
    except (OSError, SyntaxError, Image.DecompressionBombWarning, Image.DecompressionBombError) as error:
        raise ValueError('qq_asset_invalid_image') from error


CALENDAR_ART = CalendarArt()
