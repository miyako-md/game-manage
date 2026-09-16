import copy

import pytest

from game_assistant.nte_gacha import GachaError, GachaStore


def document():
    def row(uid, ordinal, rank='B', kind='item', result='dice'):
        return dict(uid=uid, pool_group_id='Lottery_LimitedCharacter',
                    timestamp='2026-09-16 12:00:00', timestamp_group_ordinal=ordinal,
                    reward_id=uid, reward_rank=rank, reward_type=kind,
                    result_type=result, quantity=1)
    return dict(format='nte-history-export', format_version=1, user_uid='77',
                banner={'id': 'Lottery_LimitedCharacter'}, scan={'warnings': [], 'skipped_records': 0},
                records=[row('new', 0), row('fashion', 1, 'S', 'item'),
                         row('gift', 2, 'S', 'character', 'points_gift'),
                         row('old-s', 3, 'S', 'character')])


def commit(store, doc, **options):
    options = dict(latest_confirmed=True, continuity_confirmed=True, **options)
    p = store.preview('77', doc, **options)
    return store.import_document('77', doc, preview_id=p['preview_id'], **options)


def test_counts_order_gifts_and_roundtrip(tmp_path):
    store = GachaStore(tmp_path / 'g.db')
    result = commit(store, document())
    assert result['imported'] == 4
    pity = result['summary']['pools'][0]['pity']
    assert (pity['status'], pity['count']) == ('exact', 2)
    assert pity['hard_pity_remaining'] is None
    assert [r['uid'] for r in store.records('77')['records']] == ['new', 'fashion', 'gift', 'old-s']
    assert commit(store, document())['duplicates'] == 4
    store.set_rule('77', dict(pool_id='Lottery_LimitedCharacter', s_hard_pity=90,
                            reset_reward_type='character', source_note='游戏内规则，用户录入', confirmed=True))
    assert store.summary('77')['pools'][0]['pity']['hard_pity_remaining'] == 88
    other = GachaStore(tmp_path / 'other.db')
    assert commit(other, store.export('77'))['imported'] == 4
    assert other.summary('77')['pools'][0]['pity']['count'] == 2


def test_conflict_atomicity_and_role_isolation(tmp_path):
    store = GachaStore(tmp_path / 'g.db')
    commit(store, document())
    bad = document()
    bad['records'][0]['reward_id'] = 'changed'
    bad['records'].append(dict(bad['records'][0], uid='additional', timestamp_group_ordinal=4))
    with pytest.raises(GachaError):
        commit(store, bad)
    assert store.summary('77')['total_records'] == 4
    assert store.summary('88')['total_records'] == 0
    with pytest.raises(GachaError):
        store.preview('88', document())


def test_missing_latest_gap_and_unknown_type_cannot_be_confirmed_away(tmp_path):
    for index, alteration in enumerate(('gap', 'type', 'ordinal')):
        store = GachaStore(tmp_path / f'{index}.db')
        doc = document()
        if alteration == 'gap':
            doc['scan']['warnings'] = ['DID_NOT_START_AT_PAGE_1']
        elif alteration == 'type':
            doc['records'][0]['result_type'] = 'future_kind'
        else:
            doc['records'][0]['timestamp_group_ordinal'] = 10
        commit(store, doc)
        assert store.summary('77')['pools'][0]['pity']['status'] == 'unknown'
        archive = store.export('77')
        other = GachaStore(tmp_path / f'restored{index}.db')
        commit(other, archive)
        assert other.summary('77')['pools'][0]['pity']['status'] == 'unknown'


def test_lower_bound_identity_preview_and_input_rejection(tmp_path):
    store = GachaStore(tmp_path / 'g.db')
    doc = document()
    doc['records'] = doc['records'][:2]
    assert commit(store, doc)['summary']['pools'][0]['pity']['status'] == 'lower_bound'
    missing = document()
    del missing['user_uid']
    p = store.preview('77', missing)
    assert p['identity_confirmation_required']
    with pytest.raises(GachaError):
        store.import_document('77', missing, preview_id=p['preview_id'])
    for invalid in ({'gachaDetails': []}, dict(document(), format_version=True)):
        with pytest.raises(GachaError):
            store.preview('77', invalid)
    tampered = copy.deepcopy(doc)
    preview = store.preview('77', doc)
    tampered['records'][0]['reward_name'] = 'changed'
    with pytest.raises(GachaError):
        store.import_document('77', tampered, preview_id=preview['preview_id'])


def test_real_export_optional_nulls_dice_and_scan_gaps(tmp_path):
    doc = document()
    doc['records'][0].update(roll_result=6, quantity=None, reward_name=None, reward_rank=None)
    store = GachaStore(tmp_path/'null.db')
    commit(store, doc)
    row = store.records('77')['records'][0]
    assert row['roll_result'] == 6
    assert row['quantity'] is None
    assert store.summary('77')['pools'][0]['pity']['status'] == 'unknown'
    gap = document()
    gap['scan']['pages_seen'] = [1, 3]
    other = GachaStore(tmp_path/'pages.db')
    assert commit(other, gap)['summary']['pools'][0]['pity']['status'] == 'unknown'


def test_arc_missing_identity_confirmed_and_limits(tmp_path):
    doc = document()
    doc.pop('user_uid')
    pool = 'Arc_MiracleBox'
    doc['banner']['id'] = pool
    doc['records'] = [dict(r, pool_group_id=pool, source_type='miracle_box', reward_type='arc')
                      for r in doc['records'][:2]]
    for row in doc['records']:
        row.pop('result_type')
    doc['records'][1]['reward_rank'] = 'S'
    store = GachaStore(tmp_path/'arc.db')
    assert commit(store, doc, identity_confirmed=True)['summary']['pools'][0]['pity']['count'] == 1
    with pytest.raises(GachaError):
        store.preview('77', dict(document(), records=[document()['records'][0]] * 50_001))


def test_unknown_archive_cannot_override_known_gap_by_dropping_coverage(tmp_path):
    store = GachaStore(tmp_path/'archive.db')
    commit(store, document())
    archive = store.export('77')
    archive['coverage'][0]['record_uids'] = ['new']
    other = GachaStore(tmp_path/'restored.db')
    with pytest.raises(GachaError):
        commit(other, archive)


def test_source_dates_regions_rules_preserved_and_conflicts_rejected(tmp_path):
    store = GachaStore(tmp_path/'source.db')
    doc = dict(document(), server_id='23003', account_region='EU')
    result = commit(store, doc)
    pity = result['summary']['pools'][0]['pity']
    assert pity['as_of'] == pity['latest_record_at'] == '2026-09-16 12:00:00'
    assert pity['confirmed_at'].endswith('+00:00')
    store.set_rule('77', dict(pool_id='Lottery_LimitedCharacter', s_hard_pity=90,
                            reset_reward_type='character', source_note='用户确认', confirmed=True))
    archive = store.export('77')
    assert archive['server_id'] == '23003'
    assert archive['account_region'] == 'EU'
    restored = GachaStore(tmp_path/'restored.db')
    assert restored.preview('77', archive)['imported_rules'][0]['s_hard_pity'] == 90
    commit(restored, archive)
    assert restored.summary('77')['pools'][0]['pity']['hard_pity_remaining'] == 88
    with pytest.raises(GachaError):
        store.preview('77', dict(doc, server_id='23004'))


def test_known_ledger_rows_missing_inside_claimed_segment_block_exactness(tmp_path):
    store = GachaStore(tmp_path/'overlap.db')
    full = document()
    commit(store, full)
    # A later "complete" file silently loses a known newest timestamp row.
    partial = document()
    partial['records'] = [r for r in partial['records'] if r['uid'] != 'fashion']
    assert commit(store, partial)['summary']['pools'][0]['pity']['status'] == 'unknown'


def test_commit_conflict_after_preview_rolls_back_earlier_inserts(tmp_path):
    store = GachaStore(tmp_path/'race.db')
    doc = document()
    p = store.preview('77', doc)
    racing = document()
    racing['records'] = [dict(racing['records'][1], reward_id='changed-after-preview')]
    commit(store, racing)
    with pytest.raises(GachaError):
        store.import_document('77', doc, preview_id=p['preview_id'])
    assert store.records('77')['total'] == 1


def test_fifty_thousand_rows_and_source_time_order(tmp_path):
    store = GachaStore(tmp_path/'large.db')
    base = document()['records'][0]
    rows = [dict(base, uid=f'row-{i}', timestamp_group_ordinal=i) for i in range(50_000)]
    doc = dict(document(), records=list(reversed(rows)))
    result = commit(store, doc)
    assert result['imported'] == 50_000
    assert result['summary']['pools'][0]['pity']['count'] == 50_000
    assert store.records('77', limit=2)['records'][0]['uid'] == 'row-0'


def test_mystery_box_counts_single_pulls_not_reward_quantity(tmp_path):
    store = GachaStore(tmp_path/'mystery.db')
    doc = document()
    pool = 'Gashapon_MysteryBox'
    doc['banner']['id'] = pool
    doc['records'] = [dict(row, pool_group_id=pool, result_type='single_pull',
                           source_type='mystery_box', quantity=20) for row in doc['records'][:2]]
    result = commit(store, doc)['summary']['pools'][0]
    assert result['total_pulls'] == 2
    assert result['pity']['status'] == 'unknown'


def test_multi_batch_archive_requires_segments_and_restores_without_upgrading(tmp_path, monkeypatch):
    import game_assistant.nte_gacha as module
    monkeypatch.setattr(module, 'MAX_RECORDS', 5)
    store = GachaStore(tmp_path/'multi.db')
    commit(store, document())
    older = document()
    older['records'] = [dict(row, uid='older-'+row['uid'], timestamp='2026-09-15 12:00:00') for row in older['records']]
    commit(store, older)
    with pytest.raises(GachaError, match='分段'):
        store.export('77')
    restored = GachaStore(tmp_path/'pages.db')
    offset = 0
    while offset is not None:
        page = store.export('77', offset=offset, limit=3)
        assert len(page['records']) <= 3
        assert page['export_page']['total'] == 8
        assert all(not c['latest_confirmed'] and not c['continuity_confirmed'] for c in page['coverage'])
        commit(restored, page)
        offset = page['export_page']['next_offset']
    assert restored.summary('77')['total_records'] == 8
    assert restored.summary('77')['pools'][0]['pity']['status'] == 'unknown'


def test_export_page_shrinks_to_fit_real_json_bytes(tmp_path, monkeypatch):
    import json
    import game_assistant.nte_gacha as module
    store = GachaStore(tmp_path/'bytes.db')
    doc = document()
    for row in doc['records']:
        row['reward_name'] = '物' * 200
    commit(store, doc)
    monkeypatch.setattr(module, 'MAX_EXPORT_BYTES', 2200)
    with pytest.raises(GachaError, match='分段'):
        store.export('77')
    page = store.export('77', offset=0, limit=4)
    assert 0 < page['export_page']['limit'] < 4
    assert page['export_page']['next_offset'] == page['export_page']['limit']
    assert len(json.dumps(page, ensure_ascii=False, separators=(',', ':')).encode()) <= 2200
