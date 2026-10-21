"""Allowlisted challenge observations shared by web responses and QQ cards.

The input is a normalized, default-query cache envelope, never credentials or
an arbitrary upstream response. Missing records do not establish game progress.
The cloud ``combat`` snapshot stores only these projections:
``{'schema_version': 1, 'reports': [war, monument, crisis]}``.
"""
from math import isfinite

from .endfield_reports import _number, _object, _items

CHALLENGE_KINDS = ('war', 'monument', 'crisis')


def _scalar(value):
    return value if isinstance(value, str) or type(value) is int or type(value) is float and isfinite(value) else None


def _groups(value):
    result = []
    for group in _items(value):
        stages = []
        for key, difficulty in (('normalDungeon', '普通'), ('hardDungeon', '困难'), ('cruelDungeon', '险境')):
            stage = _object(group.get(key))
            if stage:
                stages.append({'name': _scalar(stage.get('name')), 'difficulty': difficulty,
                               'passed': stage.get('isPass') if type(stage.get('isPass')) is bool else None})
        result.append({'name': _scalar(group.get('name')), 'stars': _number(group.get('star')), 'stages': stages})
    return result


def build_challenge_report(value, *, kind=None):
    """Project only verified fields, preserving unknowns, zero and source time."""
    data = _object(value)
    kind = kind if kind in CHALLENGE_KINDS else data.get('kind')
    valid = kind in CHALLENGE_KINDS and data.get('kind') == kind
    available = valid and isinstance(data.get('fetched_at'), str) and bool(data['fetched_at'])
    supported = data.get('supported') if valid and type(data.get('supported')) is bool else None
    failed = bool(valid and (data.get('stale') or data.get('error')))
    summary = _object(data.get('summary'))
    records = []
    if available and supported is not False:
        for raw in _items(data.get('records')):
            item = {'id': _scalar(raw.get('id')), 'name': _scalar(raw.get('name')),
                    'start_at': _scalar(raw.get('start_at')), 'end_at': _scalar(raw.get('end_at'))}
            if kind == 'war':
                item.update(stars=_number(raw.get('stars')), weeks=[{
                    'id': _scalar(week.get('id')), 'name': _scalar(week.get('name')),
                    'stars': _number(week.get('stars')), 'groups': _groups(week.get('groups')),
                } for week in _items(raw.get('weeks'))])
            elif kind == 'monument':
                item['groups'] = _groups(raw.get('groups'))
            else:
                item.update(passed=raw.get('isPass') if type(raw.get('isPass')) is bool else None,
                            result=next((_scalar(raw.get(key)) for key in ('score', 'grade', 'result')
                                         if _scalar(raw.get(key)) is not None), None))
            records.append(item)
    honors = [{'name': _scalar(raw.get('name')), 'stars': _number(raw.get('star')),
               'first_pass_at': _scalar(raw.get('first_pass_at'))}
              for raw in _items(summary.get('honors'))] if available and kind == 'war' else []
    return {'schema_version': 1, 'kind': kind if kind in CHALLENGE_KINDS else None,
            'supported': supported, 'available': available, 'stale': failed,
            'fetched_at': data.get('fetched_at') if available else None,
            'records': records, 'honors': honors,
            'summary': {'listed_count': len(records) if available and supported is not False else None,
                        'highest': _number(summary.get('highest')) if available and kind == 'crisis' else None,
                        'challenge_count': _number(summary.get('challenge_count')) if available and kind == 'crisis' else None}}


_REPORT_KEYS = frozenset(('schema_version', 'kind', 'supported', 'available', 'stale', 'fetched_at',
                          'records', 'honors', 'summary'))


def challenge_reports(payload, *, stale=False):
    """The three per-kind projections of a stored snapshot; unknown when absent.

    ``stale`` marks every report as a failed latest read (the whole poll failed).
    """
    data = _object(payload)
    stored = {item.get('kind'): item for item in _items(data.get('reports'))} if data.get('schema_version') == 1 else {}
    result = []
    for kind in CHALLENGE_KINDS:
        report = stored.get(kind)
        if not (_REPORT_KEYS <= set(report or ()) and report['schema_version'] == 1
                and type(report['available']) is bool and isinstance(report['records'], list)
                and isinstance(report['summary'], dict) and isinstance(report['honors'], list)):
            report = build_challenge_report(None, kind=kind)
        result.append({**report, 'stale': True} if stale else report)
    return result


def merge_challenge_snapshot(previous, current):
    """A kind whose latest read failed keeps its last successful report, marked stale."""
    kept = {report['kind']: report for report in challenge_reports(previous)}
    reports = []
    for report in challenge_reports(current):
        old = kept[report['kind']]
        if not report['available'] and report['stale'] and old['available']:
            report = {**old, 'stale': True}
        reports.append(report)
    return {'schema_version': 1, 'reports': reports}
