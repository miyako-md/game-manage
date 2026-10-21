"""Synthetic Endfield reports: provider isolation, uncertainty, and full documents."""
from copy import deepcopy
from dataclasses import asdict
from io import BytesIO
from types import SimpleNamespace

from PIL import Image
import pytest
from pydantic import ValidationError

from game_assistant.accounts.models import QueryResult
from game_assistant.qq.cards import card_to_text, validate_card_document
from game_assistant.qq.commands import parse_command
from game_assistant.qq.endfield_presentation import (
    overview_document, training_document, operator_document,
    regions_document, ship_document, gacha_document,
)
from game_assistant.qq.presentation import long_document
from game_assistant.qq.query_routes import QueryBody
from tests.test_qq_unified_queries import CachedQuery, IDENTITY, service, no_external_network

NOW = '2026-10-15T02:30:00+00:00'


def synthetic_account(count=12):
    names = ['陈千语', '佩丽卡', '管理员', '莱万汀', '洁尔佩塔', '余烬', '阿列什', '大潘']
    operators = [dict(id=f'char_{index:03}', name=names[index] if index < len(names) else f'合成干员{index:02}',
        level=80-index if index < 10 else None, rarity=6 if index%3==0 else 5, potential=index%6,
        evolve_phase=3 if index<4 else 2, profession='近卫', property='物理') for index in range(count)]
    if operators:
        operators[0].update(weapon=dict(id='weapon_sample',name='合成武器 · 山河',level=80,refine_level=0,breakthrough_level=4,
            rarity=6,gem=dict(name='合成基质',terms=[dict(name='敏捷提升',cost=3),dict(name='攻击提升',cost=2)])),
            equipment=[dict(slot=slot,name='合成'+name,level=70,rarity=5) for slot,name in (
                ('bodyEquip','护甲'),('armEquip','护手'),('firstAccessory','配件一'),('secondAccessory','配件二'))],
            skills=[dict(id='skill_'+str(index),name=name,level=9 if index<2 else None) for index,name in enumerate(('普通攻击','战技','连携技','终结技'))])
    return dict(base=dict(name='合成账号 · 仅供布局预览',level=60,world_level=7,char_count=count),
        observed_at='2026-10-15T02:15:00+00:00',stamina=dict(current=0,maximum=240,expected_full_at='2026-10-16T02:15:00+00:00'),
        progress=[dict(name='每日活跃',cur=60,total=100),dict(name='每周任务',cur=0,total=100),dict(name='通行证',cur=35,total=60)],
        operators=operators,availability=dict(operators=True,regions=True,ship=True),
        regions=[dict(id='domain01',name='四号谷地',level=8,money=dict(count=0,total=100000),
            settlements=[dict(id='settlement01',name='枢纽区据点',level=4,money=12500,money_max=30000,officer_char_ids=['char_000'])],
            levels=[dict(id='area01',name='枢纽区',chests=dict(count=28,total=40),puzzles=dict(count=0,total=8),
                blackboxes=dict(count=None,total=6),equipment_chests=dict(count=3,total=None),pieces=dict(count=6,total=6))]),
            dict(id='domain02',name='武陵',level=5,money=dict(count=3200,total=None),settlements=[],settlements_available=True,levels=[])],
        ship=[dict(id='room01',name='总控中枢',level=3,operators=[dict(charId='char_000',physicalStrength=0,favorability=1200),
              dict(charId='char_001',physicalStrength=8500,favorability=None)]),
              dict(id='room02',name='制造舱',level=2,operators=[dict(charId='char_002',physicalStrength=7400,favorability=300)]),
              dict(id='room03',name='会客室',level=2,operators=[],operators_available=True)])


def synthetic_gacha():
    return dict(role_id='synthetic-only',total=151,complete=False,pools=[
        dict(key='special',label='特许寻访 · 合成卡池',kind='character',total=131,six_star=3,five_star=10,free=10,gaps=1,pending=True,
             since_last_six=dict(count=12,status='lower_bound'),history=[
                 dict(name='莱万汀',pulls=58,status='exact',obtained_at=1791950400000),
                 dict(name='余烬',pulls=61,status='lower_bound',obtained_at=1791864000000),
                 dict(name='陈千语',pulls=None,status='unknown',obtained_at=None)]),
        dict(key='weapon',label='武库交易所 · 合成卡池',kind='weapon',total=20,six_star=1,five_star=2,free=0,gaps=0,pending=False,
             since_last_six=dict(count=0,status='exact'),history=[dict(name='合成武器',pulls=20,status='exact',obtained_at=1792026000000)])])


def snapshot(payload=None, **kwargs):
    return QueryResult(synthetic_account() if payload is None else payload,NOW,kwargs.get('state','ok'),kwargs.get('complete',None))


@pytest.mark.parametrize('text,command', [('终末地 干员','roles'),('终末地角色','roles'),
    ('探索 终末地','exploration'),('终末地 帝江号','ship'),('终末地 寻访战报','gacha'),('终末地 光荣之路','honor')])
def test_endfield_natural_commands(text,command):
    parsed=parse_command(text)
    assert parsed.command==command and parsed.game=='endfield'
    QueryBody(identity=asdict(IDENTITY),command=command,game='endfield')


def test_endfield_specific_commands_do_not_leak_to_other_games():
    assert parse_command('鸣潮 帝江号').command=='help'
    with pytest.raises(ValidationError): QueryBody(identity=asdict(IDENTITY),command='ship',game='nte')
    assert parse_command('终末地 干员 陈千语').role_name=='陈千语'


def test_all_six_reports_are_safe_non_mutating_and_preserve_zero_unknown():
    source=synthetic_account();source['token']='NEVER_EXPOSE';source['operators'][0]['password']='NEVER_EXPOSE'
    before=deepcopy(source);snap=snapshot(source)
    cards=[overview_document(snap),training_document(snap),operator_document(snap,'陈千语'),
           regions_document(snap),ship_document(snap),gacha_document(snapshot(synthetic_gacha()))]
    for card in cards:
        normalized=validate_card_document(card)
        assert normalized['game']=='endfield'
        assert 'NEVER_EXPOSE' not in str(normalized)
        assert '更新时间' in card_to_text(normalized)
    assert source==before
    assert '0/240' in card_to_text(cards[0])
    assert '精炼：0' in card_to_text(cards[2])
    assert '未知/6' in card_to_text(cards[3]) and '3/未知' in card_to_text(cards[3])
    assert '心情原始值：0' in card_to_text(cards[4]) and '信赖原始值：未知' in card_to_text(cards[4])


def test_unknown_and_known_empty_have_distinct_report_states():
    unknown=card_to_text(training_document(snapshot({'operators':[]})))
    empty=card_to_text(training_document(snapshot({'operators':[],'availability':{'operators':True}})))
    assert '已采集干员：未知' in unknown and '尚未采集' in unknown
    assert '已采集干员：0' in empty and '列表为空' in empty
    stale=snapshot(synthetic_account(),state='error')
    assert '旧快照' in card_to_text(ship_document(stale))
    assert '本次账本记录为空' in card_to_text(gacha_document(snapshot({'total':0,'pools':[]})))
    assert '暂无已采集寻访记录' in card_to_text(gacha_document(snapshot({})))


def test_derived_metrics_keep_unknown_totals_and_gacha_record_boundaries():
    regions=regions_document(snapshot())
    values=[field for section in regions['sections'] for row in section['rows'] for field in row['fields']]
    equipment=next(field for field in values if field['label']=='装备制造模板')
    assert equipment['metric']['maximum'] is None and '缺' not in equipment['value']
    gacha=card_to_text(gacha_document(snapshot(synthetic_gacha())))
    assert '至少 61' in gacha and '至少 12' in gacha and '边界未知' in gacha
    assert '仅统计已同步的寻访记录' in gacha
    assert '报告准确区间均抽：39.0' in gacha


def test_reports_use_only_required_default_provider_snapshot():
    query=CachedQuery();query.add('endfield','hypergryph','hg',{'account':{'nickname':'Independent passport'},'gacha':synthetic_gacha()})
    query.add('endfield','skland','sk',{'account':synthetic_account()})
    query.add('endfield','skland','other',{'account':{'base':{'name':'NEVER OTHER'}}},default=False)
    api=service(query)
    for command in ('roles','exploration','ship','honor'):
        query.reads.clear();context={}
        result=api.query(IDENTITY,command,'endfield',image_context=context,page=2)
        assert 'Independent passport' not in result['text'] and 'NEVER OTHER' not in result['text']
        assert [(scope.account_id,cap) for scope,cap in query.reads]==[('sk','account')]
        assert len(context['grants'])==1 and context['card']['game']=='endfield'
    query.reads.clear()
    api.query(IDENTITY,'gacha','endfield')
    assert [(scope.account_id,cap) for scope,cap in query.reads]==[('hg','gacha')]
    assert query.refreshes==[]


def test_summary_keeps_two_provider_identities_without_repeated_account_reads():
    query=CachedQuery();query.add('endfield','hypergryph','hg',{'account':{'nickname':'独立通行证'},'gacha':synthetic_gacha()})
    query.add('endfield','skland','sk',{'account':synthetic_account()})
    context={};result=service(query).query(IDENTITY,'summary','endfield',image_context=context)
    card=context['card'];full=str(card)
    assert '独立通行证' in full and '合成账号' in full and '独立授权' in full
    assert len(context['grants'])==2
    assert [(scope.account_id,cap) for scope,cap in query.reads].count(('sk','account'))==1


async def test_endfield_render_rechecks_secondary_scope_before_returning_image():
    query=CachedQuery();query.add('endfield','hypergryph','hg',{'gacha':synthetic_gacha()})
    query.add('endfield','skland','sk',{'account':synthetic_account()})
    class Queue:
        renderer=SimpleNamespace(invalidate_account=lambda *args:None)
        async def render(self,scope,result,**kwargs):
            assert len(result.payload['scopes'])==2
            query.versions['sk']+=1
            return b'png'
    result=await service(query,queue=Queue()).query_reply(IDENTITY,'summary','endfield',image_requested=True,budget_seconds=5)
    assert 'image' not in result and '变更' in result['text']


def test_full_roster_keeps_all_names():
    source=synthetic_account(60)
    source['operators'][1]['name']='合成的较长干员名称用于检验两行布局'
    card=long_document(training_document(snapshot(source)))
    rows=card['sections'][1]['rows']
    assert len(rows)==60 and '合成干员59' in [row['title'] for row in rows]


def test_unrenderable_large_roster_has_explicit_limit_notice():
    card=long_document(training_document(snapshot(synthetic_account(300))))
    assert any('上限' in notice and '省略' in notice for notice in card['notices'])
    assert len(card['sections'][1]['rows'])<=256


def test_public_operator_catalog_matches_name_after_unmapped_game_id():
    from game_assistant.qq.assets import PublicAssetCache, sanitize_image
    from game_assistant.qq.public_asset_catalog import CATALOG
    from game_assistant.qq.presentation import image_ref
    cache=PublicAssetCache();catalog=CATALOG['games']['endfield']['role']
    marker=BytesIO();Image.new('RGB',(120,120),(12,94,163)).save(marker,format='PNG')
    refs={}
    for name in ('佩丽卡','祀'):
        ref=cache.register_url(catalog[name]);assert ref is not None
        assert image_ref(cache,'endfield','role',name)==ref
        cache._store(ref,sanitize_image(marker.getvalue()));refs[name]=ref
    source=synthetic_account();source['operators'][0]['name']='祀'
    card=long_document(training_document(snapshot(source),cache),asset_cache=cache)
    rows={row['title']:row for row in card['sections'][1]['rows']}
    assert rows['佩丽卡']['image']==refs['佩丽卡'] and rows['祀']['image']==refs['祀']
    assert 'image' not in rows['管理员'] and image_ref(cache,'endfield','role','管理员') is None
    detail=operator_document(snapshot(source),'佩丽卡',cache)
    assert detail['image']==image_ref(cache,'endfield','portrait','佩丽卡')
    assert detail['image']!=refs['佩丽卡']


def test_ambiguous_endministrator_never_chooses_a_gender_but_explicit_variant_is_allowed():
    from game_assistant.qq.assets import PublicAssetCache
    from game_assistant.qq.endfield_presentation import _image
    cache=PublicAssetCache()
    assert _image(cache,'role',dict(id='unknown-instance',name='管理员')) is None
    first=_image(cache,'role',dict(id='endministrator1',name='管理员'))
    second=_image(cache,'role',dict(id='endministrator2',name='管理员'))
    assert first and second and first!=second


@pytest.mark.parametrize('progress,expected', [
    ([], '任务进度未知'),
    ([{'id':'daily','name':'每日活跃','cur':None,'total':100}], '任务进度未知'),
    ([{'id':'daily','name':'每日活跃','cur':100,'total':100}], '已同步任务暂无待办，部分进度未知'),
    ([{'id':'daily','name':'每日活跃','cur':100,'total':100},
      {'id':'weekly','name':'每周任务','cur':None,'total':100}], '已同步任务暂无待办，部分进度未知'),
    ([{'id':'daily','name':'每日活跃','cur':100,'total':100},
      {'id':'weekly','name':'每周任务','cur':100,'total':100}], '已同步的每日与每周任务已完成'),
])
def test_empty_todos_respect_unknown_partial_and_complete_task_progress(progress,expected):
    card=overview_document(snapshot({'progress':progress}),focus='progress')
    section=next(item for item in card['sections'] if item['category']=='ef_todos')
    assert section['fields']==[{'label':'状态','value':expected}]
    assert '今日日常已完成' not in card_to_text(card)


def test_known_incomplete_tasks_remain_todos_even_when_other_progress_is_unknown():
    card=overview_document(snapshot({'progress':[
        {'id':'daily','name':'每日活跃','cur':60,'total':100},
        {'id':'weekly','name':'每周任务','cur':None,'total':100},
    ]}),focus='progress')
    section=next(item for item in card['sections'] if item['category']=='ef_todos')
    assert section['fields']==[{'label':'每日活跃','value':'还差 40'}]
