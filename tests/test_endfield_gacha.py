"""终末地寻访账本：分页续传、断档与统计口径（离线假客户端，每页 5 条）。"""
import httpx
import pytest
from fastapi import FastAPI

from game_assistant.adapters.endfield.hypergryph import EndfieldError
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
    assert used == 1 + 3 + 3  # 武器池列表 + 特许三页 + 其余三类各一页空结果
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
    assert client.cursors == [None, None, None, None]  # 每个角色池只请求最新一页
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


async def test_an_inclusive_cursor_still_walks_to_the_window_end(tmp_path):
    store = EndfieldGachaStore(tmp_path / "g.sqlite3")
    client = FakeClient(special=history(1, 17, six={2}), inclusive=True)
    await sync(store, client)
    assert (pool(store).total, pool(store).gaps) == (17, 0)
    assert pool(store).since_last_six.model_dump() == {"count": 15, "status": "exact"}


async def test_a_failed_page_keeps_fetched_records_and_resumes_later(tmp_path):
    store = EndfieldGachaStore(tmp_path / "g.sqlite3")
    client = FakeClient(special=history(1, 20), fail_on="16")
    with pytest.raises(EndfieldError):
        await sync(store, client)
    assert (pool(store).total, pool(store).pending) == (5, True)
    client.fail_on = None
    await sync(store, client)
    assert (pool(store).total, pool(store).pending, pool(store).gaps) == (20, False, 0)


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
    assert client.cursors == [None] * 4  # 永久断档不再续传


async def test_free_pulls_turn_the_count_into_a_lower_bound(tmp_path):
    store = EndfieldGachaStore(tmp_path / "g.sqlite3")
    rows = history(1, 8, six={2})
    rows[0]["isFree"] = True
    await sync(store, FakeClient(special=rows))
    special = pool(store)
    assert special.free == 1
    assert special.since_last_six.model_dump() == {"count": 5, "status": "lower_bound"}


async def test_weapon_pools_roles_and_public_records_are_isolated(tmp_path):
    store = EndfieldGachaStore(tmp_path / "g.sqlite3")
    weapon = [{"seqId": "501", "weaponId": "w1", "weaponName": "寒夜幽影", "weaponType": "施术单元",
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


async def test_invalid_records_fail_closed_without_writing(tmp_path):
    store = EndfieldGachaStore(tmp_path / "g.sqlite3")
    rows = history(1, 3)
    rows[1]["seqId"] = "abc"
    with pytest.raises(ValueError):
        await sync(store, FakeClient(special=rows))
    assert store.summary("r1").pools == []


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
        exported = await client.get("/api/endfield/gacha/export")
        assert "attachment" in exported.headers["content-disposition"]
        assert (await client.get("/api/endfield/gacha/summary", headers={"Origin": "https://evil.invalid"})).status_code == 403
