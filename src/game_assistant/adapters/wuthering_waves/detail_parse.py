"""Lossless field normalization with URL sanitization and season validation."""
import re
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from .data_models import BaseProfile


def parse_profile(raw: dict) -> dict:
    if not isinstance(raw, dict) or not raw:
        raise ValueError('账号资料缺失')
    return BaseProfile.model_validate(normalize(raw)).model_dump(exclude_unset=True)


def parse_report(raw: dict) -> dict:
    if not isinstance(raw, dict) or not any(key in raw for key in ('totalStar', 'totalCoin', 'itemList')):
        raise ValueError('资源报告缺失')
    for key in ('itemList', 'coinList', 'starList'):
        if key in raw and raw[key] is not None and not isinstance(raw[key], list):
            raise ValueError('资源报告结构异常')
    return normalize(raw)


def normalize(value):
    if isinstance(value, list):
        return [normalize(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        name = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2',
                      re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', str(key))).lower()
        # Image/source URLs are untrusted source data, never executable schemes.
        if isinstance(item, str) and any(word in name for word in ('url', 'icon', 'image', 'bg')):
            if item:
                parts = urlsplit(item)
                if parts.scheme not in ('http', 'https') or not parts.netloc:
                    item = None
        result[name] = normalize(item)
    return result


def parse_tower(raw: dict, now: datetime) -> dict:
    remaining = raw.get('seasonEndTime')
    if isinstance(remaining, bool) or not isinstance(remaining, (int, float)) or not 0 < remaining <= 366 * 86400000:
        raise ValueError('深境区周期数据已过期或缺失')
    if not isinstance(raw.get('difficultyList'), list):
        raise ValueError('深塔分区数据缺失')
    return {**normalize(raw), 'season_end_at': (now + timedelta(milliseconds=remaining)).isoformat()}


def parse_periods(raw: dict) -> dict:
    if not isinstance(raw, dict) or not any(key in raw for key in ('weeks', 'months', 'versions')):
        raise ValueError('资源周期列表缺失')
    result = {}
    for kind, key in [('week', 'weeks'), ('month', 'months'), ('version', 'versions')]:
        rows = raw.get(key, [])
        if not isinstance(rows, list):
            raise ValueError('资源周期列表异常')
        result[kind] = [{'period': str(row['index']), 'title': row.get('title')}
                        for row in rows if isinstance(row, dict) and row.get('index') is not None]
    return result
