from fastapi.testclient import TestClient
import pytest
from game_assistant.api import create_app
from game_assistant.config import Settings
from game_assistant.registry import GameRegistry
from game_assistant.adapters.league_of_legends.adapter import LeagueOfLegendsAdapter
from game_assistant.adapters.league_of_legends.lcu_client import LcuError, LcuUnavailableError


def client(tmp_path):
    settings = Settings(db_path=str(tmp_path / 'assistant.db'))
    registry = GameRegistry()
    registry.register(LeagueOfLegendsAdapter(settings))
    app = create_app(registry=registry, settings=settings, start_scheduler=False)
    return TestClient(app, base_url='http://localhost'), app


def test_empty_archive_and_offline_collection_are_explicit(tmp_path, monkeypatch):
    c, app = client(tmp_path)
    def offline(_):
        raise LcuUnavailableError('offline')
    monkeypatch.setattr(LeagueOfLegendsAdapter, '_discover', offline)
    r = c.get('/api/lol/analysis')
    assert r.status_code == 200
    assert r.json()['account'] is None
    assert r.json()['coverage']['archived_games'] == 0
    assert r.headers['cache-control'] == 'no-store'
    assert c.post('/api/lol/collect').status_code == 403
    assert c.post('/api/lol/collect', headers={'X-Game-Assistant':'1'}).status_code == 503
    assert c.get('/api/lol/analysis?days=-1').status_code == 422
    assert c.get('/api/lol/analysis', headers={'Origin':'https://evil.example'}).status_code == 403


def test_collect_deduplicates_and_records_partial_failure_without_losing_game(tmp_path, monkeypatch):
    from game_assistant import lol_routes
    calls = []
    raw = {'gameId':123,'gameCreation':1789000000000,'queueId':2400,
           'participants':[{'participantId':1,'championId':1,'teamId':100,'stats':{'kills':0,'deaths':1,'assists':0}}],
           'participantIdentities':[{'participantId':1,'player':{'puuid':'fixture-owner'}}]}
    class FakeLCU:
        def __init__(self, **_): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass
        async def current_summoner(self): return {'puuid':'fixture-owner','gameName':'测试召唤师'}
        async def match_history(self, _): return {'games':{'games':[raw,raw]}}
        async def game_detail(self, match_id):
            calls.append(match_id)
            raise LcuError('secret-must-not-leak')
    monkeypatch.setattr(lol_routes, 'LcuClient', FakeLCU)
    monkeypatch.setattr(LeagueOfLegendsAdapter, '_discover', lambda _: ('1234','private-token'))
    c, app = client(tmp_path)
    result = c.post('/api/lol/collect',headers={'X-Game-Assistant':'1'})
    assert result.status_code == 200
    assert result.json()['games'] == 1
    assert result.json()['failed_details'] == 1
    assert calls == ['123']
    assert 'secret' not in result.text and 'private-token' not in result.text
    analysis = c.get('/api/lol/analysis?days=0').json()
    assert analysis['account']['nickname'] == '测试召唤师'
    assert analysis['coverage']['archived_games'] == 1
    assert c.get('/api/lol/matches/123').status_code == 200
    assert c.get('/api/lol/matches/999').status_code == 404


@pytest.mark.parametrize('history_has_augments',[True,False])
def test_collect_enriches_existing_complete_metrics_with_later_augments(tmp_path, monkeypatch, history_has_augments):
    from copy import deepcopy
    from game_assistant import lol_routes
    raw = {'gameId':987, 'gameCreation':1789000000000, 'queueId':2400,
           'teams':[{'teamId':100,'win':True},{'teamId':200,'win':False}],
           'participantIdentities':[{'participantId':i,'player':{'puuid':'fixture-owner' if i==1 else f'fixture-{i}'}} for i in range(1,11)],
           'participants':[{'participantId':i,'teamId':100 if i<=5 else 200,
                            'stats':{k:0 for k in ('kills','deaths','assists','totalDamageDealtToChampions','goldEarned','totalDamageTaken','timeCCingOthers')}} for i in range(1,11)]}
    updated = deepcopy(raw)
    updated['participants'][0]['stats']['playerAugment1']=100
    calls=[]
    class FakeLCU:
        def __init__(self, **_): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass
        async def current_summoner(self): return {'puuid':'fixture-owner'}
        async def match_history(self, _): return {'games':{'games':[updated if history_has_augments else raw]}}
        async def game_detail(self, mid): calls.append(mid); return updated
    monkeypatch.setattr(lol_routes, 'LcuClient', FakeLCU)
    monkeypatch.setattr(LeagueOfLegendsAdapter, '_discover', lambda _: ('1234','private-token'))
    c, app=client(tmp_path)
    app.state.lol_archive.save({'puuid':'fixture-owner'},[raw])
    assert c.post('/api/lol/collect',headers={'X-Game-Assistant':'1'}).status_code==200
    assert app.state.lol_archive.detail('fixture-owner','987')['participants'][0]['stats']['playerAugment1']==100
    assert len(calls)==(0 if history_has_augments else 1)
