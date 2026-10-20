"""终末地寻访账本：分页续传、断档与统计口径（离线假客户端，每页 5 条）。"""
import httpx
import pytest
import sqlite3
from fastapi import FastAPI

from game_assistant.adapters.endfield.hypergryph import EndfieldError
from game_assistant.adapters.endfield.endpoints import CHAR_POOL_TYPES
from game_assistant.config import Settings
from game_assistant.endfield_gacha import EndfieldGachaStore
from game_assistant.endfield_gacha_routes import install_endfield_gacha_routes

SPECIAL = "E_CharacterGachaPoolType_Special"


def rec(seq, rarity=4, name=None, free=False):
    return {"seqId": str(seq), "charId": f"c{seq}", "charName": name or f"干员{seq}", "rarity": rarity,
            "poolId": "special_1", "poolName": "冬猎", "isFree": free, "isNew": False,
            "gachaTs": str(1_780_000_000_000 + seq * 1000)}


def history(first, last, six=()):
    """seqId 由新到旧，与官方分页顺序一致。"""
    return [rec(seq, 6 if seq in six else 4) for seq in range(last, first - 1, -1)]


class FakeClient:
    def __init__(self, special=None, weapons=None, fail_on=None, inclusive=False):
        self.special = special or []
        self.weapons = weapons or {}
        self.fail_on = fail_on
        self.inclusive = inclusive  # 下一页是否从游标那条本身开始
        self.cursors = []

    def _page(self, rows, seq_id):
        self.cursors.append(seq_id)
        if seq_id is not None and seq_id == self.fail_on:
            raise EndfieldError("网络错误: ReadTimeout")
        start = 0 if seq_id is None else next(i for i, row in enumerate(rows) if row["seqId"] == seq_id) + (not self.inclusive)
        return {"list": rows[start:start + 5], "hasMore": start + 5 < len(rows)}

    async def char_records(self, u8_token, pool_type, seq_id=None):
        assert u8_token == "u8"
        return self._page(self.special if pool_type == SPECIAL else [], seq_id)

    async def weapon_pools(self, u8_token):
        return [{"poolId": pool_id, "poolName": name} for pool_id, (name, _) in self.weapons.items()]

    async def weapon_records(self, u8_token, pool_id, seq_id=None):
        return self._page(self.weapons[pool_id][1], seq_id)


async def no_sleep(_):
    pass


async def sync(store, client, budget=100, role="r1"):
    return await store.sync(role, client, "u8", budget=budget, interval=0, sleep=no_sleep)


def pool(store, key=SPECIAL, role="r1"):
    return next(p for p in store.summary(role).pools if p.key == key)


async def test_first_sync_walks_to_window_end_and_counts_since_last_six_star(tmp_path):
    store = EndfieldGachaStore(tmp_path / "g.sqlite3")
    client = FakeClient(special=history(101, 112, six={105}))
    used = await sync(store, client)
    assert used == 1 + 3 + 4  # 武器池列表 + 特许三页 + 其余四类各一页空结果
    special = pool(store)
    assert (special.total, special.six_star, special.gaps, special.pending) == (12, 1, 0, False)
    assert special.since_last_six.model_dump() == {"count": 7, "status": "exact"}
    # 窗口起点之前是否还有抽数未知，第一条 6★ 只能给出下限。
    assert [(h.name, h.pulls, h.status) for h in special.history] == [("干员105", 5, "lower_bound")]
    assert store.summary("r1").complete


async def test_incremental_sync_stops_at_known_records(tmp_path):
    store = EndfieldGachaStore(tmp_path / "g.sqlite3")
    client = FakeClient(special=history(101, 112, six={105}))
    await sync(store, client)
    client.special = history(101, 115, six={105})
    client.cursors = []
    await sync(store, client)
    assert client.cursors == [None] * 5  # 每个角色池只请求最新一页
    assert pool(store).total == 15 and pool(store).since_last_six.count == 10


async def test_budget_exhaustion_leaves_a_gap_that_the_next_sync_resumes(tmp_path):
    store = EndfieldGachaStore(tmp_path / "g.sqlite3")
    client = FakeClient(special=history(1, 30, six={3, 28}))
    assert await sync(store, client, budget=3) == 3
    partial = pool(store)
    assert (partial.total, partial.pending) == (10, True)
    assert not store.summary("r1").complete
    # 断档在 seq 21 之下：最近一次 6★ 之后仍连续，确定；这次 6★ 本身的抽数只能给下限。
    assert partial.since_last_six.model_dump() == {"count": 2, "status": "exact"}
    assert [(h.pulls, h.status) for h in partial.history] == [(8, "lower_bound")]
    await sync(store, client)
    done = pool(store)
    assert (done.total, done.gaps, done.pending) == (30, 0, False)
    assert done.since_last_six.model_dump() == {"count": 2, "status": "exact"}
    assert [(h.pulls, h.status) for h in done.history] == [(25, "exact"), (3, "lower_bound")]
    assert store.summary('r1').complete is True


async def test_budget_at_pool_boundary_keeps_unvisited_pools_pending(tmp_path):
    store = EndfieldGachaStore(tmp_path / 'g.sqlite3')
    client = FakeClient(special=history(1, 5))
    assert await sync(store, client, budget=2) == 2
    summary = store.summary('r1')
    # The first pool ended cleanly. The other four pools have not been read.
    assert summary.pools[0].pending is False and summary.pools[0].gaps == 0
    assert summary.complete is False and summary.report['pending'] is True
    # The state survives closing/reopening the ledger.
    store = EndfieldGachaStore(store.path)
    assert store.summary('r1').complete is False
    await sync(store, client)
    assert store.summary('r1').complete is True


async def test_empty_unvisited_and_successfully_scanned_pools_are_distinct(tmp_path):
    store = EndfieldGachaStore(tmp_path / 'g.sqlite3')
    unseen = store.summary('r1')
    assert unseen.total == 0 and unseen.complete is None and unseen.report['pending'] is None
    await sync(store, FakeClient(), budget=1)  # Discovery used the entire budget.
    pending = store.summary('r1')
    assert pending.pools == [] and pending.total == 0
    assert pending.complete is False and pending.report['pending'] is True
    await sync(store, FakeClient())
    empty = store.summary('r1')
    assert empty.pools == [] and empty.complete is True and empty.report['pending'] is False
    assert store.summary('another-role').complete is None


async def test_discovered_weapon_pool_must_be_scanned_even_when_all_character_pools_are_empty(tmp_path):
    store = EndfieldGachaStore(tmp_path / 'g.sqlite3')
    client = FakeClient(weapons={'weapon_1': ('合成武器池', [])})
    await sync(store, client, budget=1 + len(CHAR_POOL_TYPES))
    summary = store.summary('r1')
    assert summary.total == 0 and summary.pools == []
    assert summary.complete is False and summary.report['pending'] is True
    await sync(store, client)
    assert store.summary('r1').complete is True


@pytest.mark.parametrize('failure', ['discovery', 'first_page'])
async def test_failed_scan_retains_success_time_and_cannot_claim_completion(tmp_path, failure):
    store = EndfieldGachaStore(tmp_path / 'g.sqlite3')
    await sync(store, FakeClient(special=history(1, 5)))
    successful = pool(store).last_sync_at

    class FailedClient(FakeClient):
        async def weapon_pools(self, token):
            if failure == 'discovery':
                raise EndfieldError('synthetic catalog failure')
            return await super().weapon_pools(token)

        async def char_records(self, token, pool_type, seq_id=None):
            raise EndfieldError('synthetic first page failure')

    # Every pool this run tried failed, so the run itself reports the failure.
    with pytest.raises((EndfieldError, ValueError)):
        await sync(store, FailedClient())
    failed = store.summary('r1')
    assert failed.complete is False and failed.report['pending'] is True
    assert pool(store).last_sync_at == successful and pool(store).total == 5
    await sync(store, FakeClient(special=history(1, 5)))
    assert store.summary('r1').complete is True


@pytest.mark.parametrize('all_pools,successful,pending_break,expected', [
    (False, True, False, None), (True, False, False, None),
    (True, True, False, True), (True, True, True, False),
])
def test_legacy_coverage_is_inferred_only_from_successful_scans(tmp_path, all_pools, successful, pending_break, expected):
    path = tmp_path / 'legacy.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE pools(role TEXT NOT NULL,pool_key TEXT NOT NULL,kind TEXT NOT NULL,'
                   'label TEXT NOT NULL,last_sync_at TEXT,PRIMARY KEY(role,pool_key))')
        for key, label in (CHAR_POOL_TYPES.items() if all_pools else [(SPECIAL, '特许寻访')]):
            db.execute('INSERT INTO pools VALUES(?,?,?,?,?)',
                       ('r1', key, 'character', label, '2026-10-15T00:00:00Z' if successful else None))
    store = EndfieldGachaStore(path)
    if pending_break:
        with sqlite3.connect(path) as db:
            db.execute('INSERT INTO breaks VALUES(?,?,?,0)', ('r1', SPECIAL, 5))
    summary = store.summary('r1')
    assert summary.complete is expected
    assert summary.report['pending'] is (None if expected is None else not expected)
    assert EndfieldGachaStore(path).summary('r1').complete is expected


async def test_an_inclusive_cursor_still_walks_to_the_window_end(tmp_path):
    store = EndfieldGachaStore(tmp_path / "g.sqlite3")
    client = FakeClient(special=history(1, 17, six={2}), inclusive=True)
    await sync(store, client)
    assert (pool(store).total, pool(store).gaps) == (17, 0)
    assert pool(store).since_last_six.model_dump() == {"count": 15, "status": "exact"}


async def test_a_failed_page_keeps_fetched_records_and_resumes_later(tmp_path):
    store = EndfieldGachaStore(tmp_path / "g.sqlite3")
    client = FakeClient(special=history(1, 20), fail_on="16")
    await sync(store, client)  # the other pools succeed, so the run does not fail as a whole
    assert (pool(store).total, pool(store).pending) == (5, True)
    assert [(e.key, e.label, e.message) for e in store.summary("r1").errors] == [(SPECIAL, "特许寻访", "网络错误: ReadTimeout")]
    client.fail_on = None
    await sync(store, client)
    assert (pool(store).total, pool(store).pending, pool(store).gaps) == (20, False, 0)
    assert store.summary("r1").errors == []


async def test_window_moving_past_old_records_leaves_a_permanent_gap(tmp_path):
    store = EndfieldGachaStore(tmp_path / "g.sqlite3")
    client = FakeClient(special=history(1, 5, six={2}))
    await sync(store, client)
    client.special = history(90, 100)  # 旧记录已滑出官方窗口
    await sync(store, client)
    special = pool(store)
    assert (special.total, special.gaps, special.pending) == (16, 1, False)
    assert store.summary("r1").complete
    assert special.since_last_six.model_dump() == {"count": 11, "status": "lower_bound"}
    client.cursors = []
    await sync(store, client)
    assert client.cursors == [None] * 5  # 永久断档不再续传


async def test_free_pulls_turn_the_count_into_a_lower_bound(tmp_path):
    store = EndfieldGachaStore(tmp_path / "g.sqlite3")
    rows = history(1, 8, six={2})
    rows[0]["isFree"] = True
    await sync(store, FakeClient(special=rows))
    special = pool(store)
    assert special.free == 1
    assert special.since_last_six.model_dump() == {"count": 5, "status": "lower_bound"}


async def test_rerun_is_fetched_and_kept_separate_from_special(tmp_path):
    rerun = 'E_CharacterGachaPoolType_Rerun'

    class RerunClient(FakeClient):
        async def char_records(self, u8_token, pool_type, seq_id=None):
            if pool_type == rerun:
                rows = [{**row, 'poolId': 'rerun_1', 'poolName': '绚丽异彩'}
                        for row in history(10, 12, six={11})]
                return self._page(rows, seq_id)
            return await super().char_records(u8_token, pool_type, seq_id)

    store = EndfieldGachaStore(tmp_path / 'g.sqlite3')
    await sync(store, RerunClient(special=history(1, 4)))
    assert [(entry.label, entry.total) for entry in store.summary('r1').pools] == [
        ('特许寻访', 4), ('重构寻访', 3)]
    assert pool(store, rerun).since_last_six.count == 1
    assert len(store.export('r1')['records']) == 7


@pytest.mark.parametrize('missing', ['rarity', 'isFree'])
async def test_missing_pull_attributes_cannot_produce_exact_pity(tmp_path, missing):
    store = EndfieldGachaStore(tmp_path / 'g.sqlite3')
    rows = history(1, 3, six={1})
    rows[1].pop(missing)
    await sync(store, FakeClient(special=rows))
    assert pool(store).since_last_six.model_dump() == {'count':1, 'status':'lower_bound'}
    # A later known six-star establishes a new continuous segment.
    rows = history(1, 6, six={1, 5})
    rows[4].pop(missing)
    await sync(store, FakeClient(special=rows))
    summary = pool(store)
    assert summary.history[0].status == 'lower_bound'
    assert summary.since_last_six.model_dump() == {'count':1, 'status':'exact'}


async def test_weapon_pools_roles_and_public_records_are_isolated(tmp_path):
    store = EndfieldGachaStore(tmp_path / "g.sqlite3")
    weapon = [{"seqId": "501", "kind": "draw", "weaponId": "w1", "weaponName": "寒夜幽影", "weaponType": "施术单元",
               "rarity": 6, "poolId": "weapon_1", "poolName": "幽寒申领", "isNew": True, "gachaTs": "1780000000"}]
    await sync(store, FakeClient(special=history(1, 3), weapons={"weapon_1": ("幽寒申领", weapon)}))
    summary = store.summary("r1")
    assert [p.key for p in summary.pools] == [SPECIAL, "weapon:weapon_1"]
    assert pool(store, "weapon:weapon_1").history[0].obtained_at == 1_780_000_000_000
    assert store.summary("someone-else").pools == []
    page = store.records("r1", "weapon:weapon_1")
    assert page["total"] == 1 and page["records"][0]["seq_id"] == "501"
    exported = store.export("r1")
    assert exported["format"] == "game-assistant-endfield-gacha" and len(exported["records"]) == 4
    assert all(isinstance(row["seq_id"], str) for row in exported["records"])


def weapon_draws(first, last, six=(), pool_id='weapon_1', version=None):
    return [{"seqId": str(seq), "kind": "draw", "weaponId": f"w{seq}",
             "weaponName": f"合成武器{seq}", "nameText": f"合成武器{seq}", "rarity": 6 if seq in six else 4,
             "poolId": pool_id, "poolName": "合成申领", "poolVersion": version,
             "gachaTs": str(1_780_000_000_000 + seq * 1000)} for seq in range(last, first - 1, -1)]


async def test_weapon_draws_without_is_free_count_but_gifts_do_not_reset_pity(tmp_path):
    store = EndfieldGachaStore(tmp_path / 'g.sqlite3')
    rows = weapon_draws(1, 10, six={3, 8})
    gifts = [dict(rows[0], seqId='12', kind='gift_weapon', rarity=6, nameText='额外武器'),
             {'seqId':'11', 'kind':'gift_weapon_box', 'nameText':'补充武库箱', 'poolId':'weapon_1',
              'poolName':'合成申领', 'giftRewardLabel':'累计申领奖励', 'gachaTs':'1780000011000'}]
    await sync(store, FakeClient(weapons={'weapon_1':('合成申领', gifts + rows)}))
    summary = pool(store, 'weapon:weapon_1')
    assert (summary.total, summary.six_star, summary.four_star, summary.unknown_rarity, summary.gifts) == (10, 2, 8, 0, 2)
    assert summary.since_last_six.model_dump() == {'count':2, 'status':'exact'}
    assert [(item.pulls,item.status) for item in summary.history] == [(5,'exact'),(3,'lower_bound')]
    assert summary.banners[0].total == 10
    ledger = store.records('r1',kind='weapon')
    assert ledger['total'] == 12
    assert ledger['records'][0]['name'] == '额外武器'
    assert ledger['records'][1]['reward_label'] == '累计申领奖励'
    assert len(store.export('r1')['records']) == 12


async def test_gift_only_weapon_pool_has_no_pull_or_pity_statistics(tmp_path):
    store = EndfieldGachaStore(tmp_path / 'g.sqlite3')
    row = dict(weapon_draws(1,1)[0], kind='gift', rarity=6, nameText='额外奖励')
    await sync(store, FakeClient(weapons={'weapon_1':('合成申领',[row])}))
    summary = pool(store, 'weapon:weapon_1')
    assert (summary.total,summary.six_star,summary.gifts,summary.history) == (0,0,1,[])
    assert summary.since_last_six.model_dump() == {'count':None,'status':'unknown'}


@pytest.mark.parametrize('record_kind',[None,'unrecognised',''])
async def test_unclassified_weapon_records_do_not_prove_draw_or_pity_counts(tmp_path,record_kind):
    store=EndfieldGachaStore(tmp_path/'g.sqlite3')
    rows=weapon_draws(1,2,six={1})
    for row in rows:
        if record_kind is None:row.pop('kind')
        else:row['kind']=record_kind
    client=FakeClient(weapons={'weapon_1':('合成申领',rows)})
    await sync(store,client)
    summary=pool(store,'weapon:weapon_1')
    assert (summary.total,summary.six_star,summary.unverified_records)==(0,0,2)
    assert summary.history==[] and summary.since_last_six.status=='unknown'
    assert store.records('r1',kind='weapon')['total']==2
    for row in rows:row['kind']='draw'
    await sync(store,client)
    repaired=pool(store,'weapon:weapon_1')
    assert (repaired.total,repaired.unverified_records)==(2,0)
    assert repaired.since_last_six.model_dump()=={'count':1,'status':'exact'}


def make_weapon_payloads_legacy(store):
    import json
    with store._db() as db:
        for role,key,seq,payload in db.execute("SELECT * FROM records WHERE pool_key LIKE 'weapon:%'").fetchall():
            row=json.loads(payload)
            for field in ('record_kind','pool_version','reward_label'):
                row.pop(field,None)
            db.execute('UPDATE records SET payload=? WHERE role=? AND pool_key=? AND seq_id=?',
                       (json.dumps(row),role,key,seq))


async def test_legacy_weapon_rows_are_refetched_across_known_pages_and_repaired_in_place(tmp_path):
    store = EndfieldGachaStore(tmp_path / 'g.sqlite3')
    rows = weapon_draws(1,14,six={3,8,12})
    gift = dict(rows[0],seqId='15',kind='gift_weapon',rarity=6,nameText='额外奖励')
    client = FakeClient(weapons={'weapon_1':('合成申领',[gift]+rows)})
    await sync(store,client)
    make_weapon_payloads_legacy(store)
    assert (pool(store,'weapon:weapon_1').total,pool(store,'weapon:weapon_1').unverified_records) == (0,15)
    # A bounded migration must resume behind newly verified head rows.
    await sync(store,client,budget=8)
    assert pool(store,'weapon:weapon_1').unverified_records == 5
    await sync(store,client)
    repaired = pool(store,'weapon:weapon_1')
    assert (repaired.total,repaired.gifts,repaired.unverified_records) == (14,1,0)
    assert repaired.since_last_six.model_dump() == {'count':2,'status':'exact'}
    assert store.records('r1',kind='weapon')['total'] == 15
    assert all('record_kind' in row for row in store.export('r1')['records'])


async def test_expired_legacy_weapon_records_are_preserved_and_reported_as_unverified(tmp_path):
    store = EndfieldGachaStore(tmp_path / 'g.sqlite3')
    await sync(store,FakeClient(weapons={'weapon_1':('合成申领',weapon_draws(1,10,six={3,8}))}))
    make_weapon_payloads_legacy(store)
    await sync(store,FakeClient(weapons={'weapon_1':('合成申领',weapon_draws(6,10,six={8}))}))
    summary = pool(store,'weapon:weapon_1')
    assert (summary.total,summary.unverified_records,summary.six_star) == (5,5,1)
    assert store.records('r1',kind='weapon')['total'] == 10
    assert len(store.export('r1')['records']) == 10
    assert summary.since_last_six.model_dump() == {'count':2,'status':'exact'}


async def test_weapon_versions_do_not_share_a_pity_interval(tmp_path):
    store = EndfieldGachaStore(tmp_path / 'g.sqlite3')
    rows = weapon_draws(4,6,six={5},version=2)+weapon_draws(1,3,six={1},version=1)
    await sync(store,FakeClient(weapons={'weapon_1':('合成申领',rows)}))
    summary=pool(store,'weapon:weapon_1')
    assert [(row.pulls,row.status) for row in summary.history] == [(2,'lower_bound'),(1,'lower_bound')]
    assert summary.since_last_six.model_dump() == {'count':1,'status':'exact'}


async def test_weapon_records_from_a_different_pool_are_rejected_before_saving(tmp_path):
    store=EndfieldGachaStore(tmp_path/'g.sqlite3')
    await sync(store,FakeClient(weapons={'weapon_1':('合成申领',weapon_draws(1,3,pool_id='other'))}))
    assert store.records('r1')['total']==0
    assert store.summary('r1').complete is False
    assert store.summary('r1').errors[0].message=='武器记录所属卡池不一致，请刷新重试'


async def test_weapon_kind_filter_paginates_across_pools_without_operator_rows(tmp_path):
    store=EndfieldGachaStore(tmp_path/'g.sqlite3')
    await sync(store,FakeClient(special=history(1,20),weapons={
        'weapon_1':('合成申领',weapon_draws(1,3)),
        'weapon_2':('另一申领',weapon_draws(4,5,pool_id='weapon_2'))}))
    page=store.records('r1',limit=2,offset=2,kind='weapon')
    assert page['total']==5 and [r['seq_id'] for r in page['records']]==['3','2']
    assert {r['kind'] for r in page['records']}=={'weapon'}
    assert store.records('r1',SPECIAL,kind='weapon')['total']==0
    assert store.records('r1',kind='character')['total']==20
    assert store.records('other-role',kind='weapon')['total']==0
    with pytest.raises(ValueError):store.records('r1',kind='bad')


async def test_zero_weapon_cursor_is_an_end_marker_even_if_has_more_is_true(tmp_path):
    class ZeroCursor(FakeClient):
        async def weapon_records(self,token,pool_id,seq_id=None):
            assert seq_id is None
            return {'list':weapon_draws(0,2),'hasMore':True}
    store=EndfieldGachaStore(tmp_path/'g.sqlite3')
    await sync(store,ZeroCursor(weapons={'weapon_1':('合成申领',[])}))
    assert pool(store,'weapon:weapon_1').total==3
    assert store.summary('r1').complete is True


async def test_non_advancing_weapon_cursor_keeps_a_pending_gap(tmp_path):
    class StuckCursor(FakeClient):
        async def weapon_records(self,token,pool_id,seq_id=None):
            return {'list':weapon_draws(5,5),'hasMore':True}
    store=EndfieldGachaStore(tmp_path/'g.sqlite3')
    used=await sync(store,StuckCursor(weapons={'weapon_1':('合成申领',[])}),budget=8)
    assert used==8 and pool(store,'weapon:weapon_1').pending is True
    assert store.summary('r1').errors[0].message=='寻访记录分页未向前推进，请刷新重试'


async def test_invalid_records_fail_closed_without_writing(tmp_path):
    store = EndfieldGachaStore(tmp_path / "g.sqlite3")
    rows = history(1, 3)
    rows[1]["seqId"] = "abc"
    await sync(store, FakeClient(special=rows))
    assert store.summary("r1").pools == []
    assert [e.message for e in store.summary("r1").errors] == ["终末地数据格式无效，请刷新重试"]
    assert store.summary('r1').complete is False
    assert store.summary('r1').report['pending'] is True


async def test_routes_require_a_logged_in_role_and_serve_the_ledger(tmp_path):
    settings = Settings(db_path=str(tmp_path / "a.db"), auth_allowed_origins=["http://testserver"])
    app = FastAPI()
    app.state.settings = settings
    install_endfield_gacha_routes(app, settings)
    from game_assistant.api_security import install_api_security
    install_api_security(app, settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        assert (await client.get("/api/endfield/gacha/summary")).status_code == 409
        settings.endfield_role_id = "r1"
        store = EndfieldGachaStore(tmp_path / "a.endfield-gacha.sqlite3")
        await sync(store, FakeClient(special=history(1, 7, six={4})))
        summary = (await client.get("/api/endfield/gacha/summary")).json()
        assert summary["schema_version"] == 1 and summary["pools"][0]["six_star"] == 1
        page = (await client.get("/api/endfield/gacha/records?limit=2&offset=1")).json()
        assert page["total"] == 7 and [r["seq_id"] for r in page["records"]] == ["6", "5"]
        assert (await client.get("/api/endfield/gacha/records?limit=0")).status_code == 400
        assert (await client.get("/api/endfield/gacha/records?kind=weapon")).json()['total'] == 0
        assert (await client.get("/api/endfield/gacha/records?kind=character")).json()['total'] == 7
        assert (await client.get("/api/endfield/gacha/records?kind=invalid")).status_code == 400
        exported = await client.get("/api/endfield/gacha/export")
        assert "attachment" in exported.headers["content-disposition"]
        assert (await client.get("/api/endfield/gacha/summary", headers={"Origin": "https://evil.invalid"})).status_code == 403


def test_legacy_unscanned_pool_does_not_claim_known_pending_false(tmp_path):
    path=tmp_path/'legacy-coverage.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE pools(role TEXT NOT NULL,pool_key TEXT NOT NULL,kind TEXT NOT NULL,label TEXT NOT NULL,last_sync_at TEXT,PRIMARY KEY(role,pool_key))')
        db.execute('INSERT INTO pools VALUES(?,?,?,?,NULL)',('r1',SPECIAL,'character','legacy'))
    store=EndfieldGachaStore(path)
    store._add('r1',SPECIAL,[dict(seq_id=1,rarity=4,is_free=False,gacha_ts=1780000000000)])
    summary=store.summary('r1')
    assert summary.complete is None and summary.pools[0].pending is None


def test_scan_pending_addition_preserves_old_named_sql_and_sqlite_backup(tmp_path):
    from contextlib import closing
    original=tmp_path/'legacy.sqlite3';working=tmp_path/'upgrade.sqlite3';backup=tmp_path/'backup.sqlite3'
    with closing(sqlite3.connect(original)) as db:
        db.execute('CREATE TABLE pools(role TEXT NOT NULL,pool_key TEXT NOT NULL,kind TEXT NOT NULL,label TEXT NOT NULL,last_sync_at TEXT,PRIMARY KEY(role,pool_key))')
        db.executemany('INSERT INTO pools VALUES(?,?,?,?,?)',[('r1',SPECIAL,'character','legacy','2026-10-14T00:00:00Z'),('r1','unscanned','character','unknown',None)])
        db.commit()
        with closing(sqlite3.connect(working)) as target:db.backup(target)
    before=original.read_bytes();store=EndfieldGachaStore(working)
    with closing(sqlite3.connect(working)) as db:
        assert db.execute('SELECT pool_key,scan_pending FROM pools ORDER BY pool_key').fetchall()==[(SPECIAL,0),('unscanned',None)]
        # These are the deployed a2ed77c constructor/sync/export named-column statements.
        db.execute('INSERT INTO pools(role,pool_key,kind,label) VALUES(?,?,?,?) ON CONFLICT(role,pool_key) DO UPDATE SET label=excluded.label',('r1',SPECIAL,'character','old-code-updated'))
        db.execute('UPDATE pools SET last_sync_at=? WHERE role=? AND pool_key=?',('2026-10-15T00:00:00Z','r1',SPECIAL))
        assert len(db.execute('SELECT pool_key,kind,label,last_sync_at FROM pools WHERE role=?',('r1',)).fetchall())==2
        db.commit()
        with closing(sqlite3.connect(backup)) as target:db.backup(target)
        rows=db.execute('SELECT * FROM pools ORDER BY pool_key').fetchall()
    reopened=EndfieldGachaStore(working)
    with closing(sqlite3.connect(backup)) as db:assert db.execute('SELECT * FROM pools ORDER BY pool_key').fetchall()==rows
    assert original.read_bytes()==before and reopened.path==working


async def test_local_channels_with_colliding_role_ids_keep_separate_histories(tmp_path):
    from game_assistant.endfield_gacha import local_ledger_role
    store = EndfieldGachaStore(tmp_path / "g.sqlite3")
    official, bilibili = local_ledger_role("r1", "official"), local_ledger_role("r1", "bilibili")
    assert official == "r1" and bilibili != official
    await sync(store, FakeClient(special=history(1, 3)), role=official)
    await sync(store, FakeClient(special=[rec(seq, 6, name=f"B服{seq}") for seq in (3, 2, 1)]), role=bilibili)
    assert pool(store, role=official).total == 3 and pool(store, role=official).six_star == 0
    assert pool(store, role=bilibili).total == 3 and pool(store, role=bilibili).six_star == 3
    assert store.summary(bilibili).role_id == "r1"
    assert store.records(bilibili)["role_id"] == "r1"
    assert {r["name"] for r in store.records(bilibili)["records"]} == {"B服1", "B服2", "B服3"}
    assert store.export(bilibili)["role_id"] == "r1"


async def test_routes_read_the_ledger_of_the_logged_in_channel(tmp_path):
    from game_assistant.endfield_gacha import local_ledger_role
    settings = Settings(db_path=str(tmp_path / "a.db"), auth_allowed_origins=["http://testserver"],
                        endfield_role_id="r1", endfield_channel="bilibili")
    app = FastAPI()
    app.state.settings = settings
    install_endfield_gacha_routes(app, settings)
    store = EndfieldGachaStore(tmp_path / "a.endfield-gacha.sqlite3")
    await sync(store, FakeClient(special=history(1, 2)), role="r1")
    await sync(store, FakeClient(special=history(1, 5)), role=local_ledger_role("r1", "bilibili"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        summary = (await client.get("/api/endfield/gacha/summary")).json()
        assert summary["role_id"] == "r1" and summary["pools"][0]["total"] == 5
        settings.endfield_channel = "official"
        assert (await client.get("/api/endfield/gacha/summary")).json()["pools"][0]["total"] == 2


def test_adapter_scopes_only_the_local_ledger_by_channel(tmp_path):
    from game_assistant.adapters.endfield.adapter import EndfieldAdapter
    adapter = EndfieldAdapter(Settings(db_path=str(tmp_path / "a.db"), endfield_channel="bilibili"))
    assert adapter._ledger_role(adapter.gacha_store(), "r1") == "bilibili:r1"
    cloud_bridge = object()  # 云端注入的账本按授权建库，并校验原始角色 ID
    assert adapter._ledger_role(cloud_bridge, "r1") == "r1"
    adapter._settings.endfield_channel = "official"
    assert adapter._ledger_role(adapter.gacha_store(), "r1") == "r1"


async def test_a_pool_type_splits_into_its_banners_newest_first_with_six_stars_tagged(tmp_path):
    store = EndfieldGachaStore(tmp_path / "g.sqlite3")
    rows = history(1, 12, six={3, 10})
    for row in rows:  # seq 1–6 是「冬猎」，7–12 是下一期「晨星」
        if int(row["seqId"]) > 6:
            row.update(poolId="special_2", poolName="晨星")
    rows[0]["isFree"] = True
    rows[1]["rarity"] = 5
    await sync(store, FakeClient(special=rows))
    special = pool(store)
    assert [(b.pool_id, b.name, b.total, b.six_star, b.five_star, b.four_star, b.free) for b in special.banners] == [
        ("special_2", "晨星", 6, 1, 1, 4, 1), ("special_1", "冬猎", 6, 1, 0, 5, 0)]
    assert special.banners[0].oldest_at == 1_780_000_007_000 and special.banners[0].newest_at == 1_780_000_012_000
    # The 晨星 6★ interval still counts back into 冬猎: the ledger keeps one sequence per pool type.
    assert [(h.name, h.pool_id, h.pulls) for h in special.history] == [("干员10", "special_2", 7), ("干员3", "special_1", 3)]
    assert sum(b.total for b in special.banners) == special.total


class WeaponTroubleClient(FakeClient):
    """A weapon pool that errors, a healthy one, and an optional listing failure."""
    def __init__(self, *args, broken=(), listing=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.broken, self.listing = set(broken), listing

    async def weapon_pools(self, u8_token):
        if self.listing:
            raise self.listing
        return await super().weapon_pools(u8_token)

    async def weapon_records(self, u8_token, pool_id, seq_id=None):
        if pool_id in self.broken:
            raise EndfieldError("接口错误 code=1001：参数错误", status_code=1001)
        return await super().weapon_records(u8_token, pool_id, seq_id)


def weapon_rows(first, last, pool_id):
    return [{"seqId": str(seq), "kind": "draw", "weaponId": f"w{seq}", "weaponName": f"武器{seq}", "rarity": 4, "poolId": pool_id,
             "poolName": pool_id, "isNew": False, "gachaTs": str(1_780_000_000_000 + seq * 1000)} for seq in range(last, first - 1, -1)]


async def test_one_failing_weapon_pool_neither_blocks_the_others_nor_hides_its_error(tmp_path):
    store = EndfieldGachaStore(tmp_path / "g.sqlite3")
    weapons = {"w_bad": ("坏池", weapon_rows(1, 3, "w_bad")), "w_ok": ("好池", weapon_rows(11, 17, "w_ok"))}
    client = WeaponTroubleClient(special=history(1, 4), weapons=weapons, broken={"w_bad"})
    await sync(store, client)
    summary = store.summary("r1")
    assert {p.key: p.total for p in summary.pools} == {SPECIAL: 4, "weapon:w_ok": 7}
    assert [(e.key, e.label, e.message) for e in summary.errors] == [("weapon:w_bad", "坏池", "接口错误 code=1001：参数错误")]
    assert summary.complete is False
    client.broken.clear()
    await sync(store, client)
    summary = store.summary("r1")
    assert summary.errors == [] and summary.complete is True and pool(store, "weapon:w_bad").total == 3


async def test_a_failed_weapon_listing_still_syncs_operator_pools_and_stays_pending(tmp_path):
    store = EndfieldGachaStore(tmp_path / "g.sqlite3")
    client = WeaponTroubleClient(special=history(1, 4), weapons={"w1": ("武库", weapon_rows(1, 2, "w1"))},
                                 listing=EndfieldError("网络错误: ConnectTimeout"))
    await sync(store, client)
    summary = store.summary("r1")
    assert [p.key for p in summary.pools] == [SPECIAL] and summary.complete is False
    assert [(e.label, e.message) for e in summary.errors] == [("武器池列表", "网络错误: ConnectTimeout")]
    assert [p["key"] for p in store.export("r1")["pools"]] == sorted(CHAR_POOL_TYPES)
    client.listing = None
    await sync(store, client)
    summary = store.summary("r1")
    assert summary.errors == [] and summary.complete is True and pool(store, "weapon:w1").total == 2


async def test_an_expired_login_still_stops_the_whole_run(tmp_path):
    store = EndfieldGachaStore(tmp_path / "g.sqlite3")

    class Expired(WeaponTroubleClient):
        async def weapon_records(self, u8_token, pool_id, seq_id=None):
            raise EndfieldError("登录已失效", status_code=401, expired=True)

    with pytest.raises(EndfieldError):
        await sync(store, Expired(special=history(1, 4), weapons={"w1": ("武库", weapon_rows(1, 2, "w1"))}))
    assert pool(store).total == 4


async def test_empty_pages_end_a_pool_like_the_reference_clients_but_a_mid_walk_one_stays_resumable(tmp_path):
    store = EndfieldGachaStore(tmp_path / "g.sqlite3")

    class EmptyHead(FakeClient):
        async def char_records(self, u8_token, pool_type, seq_id=None):
            return {"list": [], "hasMore": True}

    await sync(store, EmptyHead())
    assert store.summary("r1").complete is True and store.summary("r1").errors == []

    class EmptyAfterFirstPage(FakeClient):
        async def char_records(self, u8_token, pool_type, seq_id=None):
            if pool_type == SPECIAL and seq_id is not None:
                return {"list": [], "hasMore": True}
            return await super().char_records(u8_token, pool_type, seq_id)

    store = EndfieldGachaStore(tmp_path / "g2.sqlite3")
    await sync(store, EmptyAfterFirstPage(special=history(1, 12)))
    assert (pool(store).total, pool(store).pending, pool(store).gaps) == (5, True, 1)


@pytest.mark.parametrize("has_more,expected", [(None, False), (0, False), (1, True), (False, False), (True, True)])
def test_record_pages_read_has_more_like_the_reference_clients(has_more, expected):
    from game_assistant.adapters.endfield import parse
    data = {"list": []} if has_more is None else {"list": [], "hasMore": has_more}
    assert parse.record_page(data, "weapon") == ([], expected)


@pytest.mark.parametrize("data", [{"list": [], "hasMore": "yes"}, {"list": [], "hasMore": 2}, {"list": [], "hasMore": 1.0},
                                  {"list": [], "hasMore": [True]}, {"hasMore": False}, {"unexpected": "response"}])
def test_record_pages_still_refuse_unrecognised_shapes(data):
    from game_assistant.adapters.endfield import parse
    with pytest.raises(ValueError):
        parse.record_page(data, "weapon")


@pytest.mark.parametrize('payload',[{}, {'list':None}, {'other':[]}])
async def test_invalid_weapon_catalog_does_not_report_a_successful_empty_scan(tmp_path,payload):
    class InvalidCatalog(FakeClient):
        async def weapon_pools(self,token):return payload
    store=EndfieldGachaStore(tmp_path/'g.sqlite3')
    await sync(store,InvalidCatalog())
    summary=store.summary('r1')
    assert summary.complete is False and summary.errors[0].key == 'weapon:*'


def test_weapon_catalog_deduplicates_the_same_pool():
    from game_assistant.adapters.endfield import parse
    assert parse.weapon_pools({'list':[{'poolId':'w','poolName':'武库'}]*2}) == [('w','武库')]
