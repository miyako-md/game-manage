from datetime import datetime
import json
import pytest
from game_assistant.qq.commands import parse_command
from game_assistant.qq.guides import reply
from game_assistant.qq.browser_rendering import validate_snapshot
from game_assistant.qq.render_snapshot import asset_requests
from game_assistant.qq.query_routes import QqQueryService
from game_assistant.qq.models import QqIdentity
from game_assistant.qq.rendering import RenderingUnavailable

@pytest.mark.parametrize('text,game,name',[
    ('攻略',None,None),('鸣潮 攻略','wuthering_waves',None),
    ('鸣潮 攻略 散华','wuthering_waves','散华'),
    ('异环 角色攻略 安魂曲','nte','安魂曲'),
    ('攻略 异环 黑羽','nte','黑羽'),('终末地 攻略 伊冯','endfield','伊冯'),
])
def test_guide_commands_are_explicit_public_catalog_queries(text,game,name):
    command=parse_command(text)
    assert (command.command,command.game,command.role_name)==('guide',game,name)

def test_guide_names_and_pages_do_not_accept_other_selectors():
    for text in ['攻略 散华','鸣潮 攻略 散华 other-account','鸣潮 攻略 散华 2']:
        assert parse_command(text).command=='help'

@pytest.mark.parametrize('game,name,kind',[('wuthering_waves','散华','guide'),('nte','安魂曲','guide'),('nte','黑羽','guide'),('endfield',None,'notice')])
def test_guides_use_public_catalog_without_bindings_or_live_accounts(game,name,kind):
    class NoBindings:
        def resolve_qq_identity(self,*args):raise AssertionError('public guide must not read bindings')
    context={};service=QqQueryService(NoBindings(),None,None,clock=lambda:datetime.fromisoformat('2026-10-18T16:30:00+08:00'))
    service.query(QqIdentity('app','group','group','sender'),'guide',game,role_name=name,image_context=context)
    snapshot=context['render_snapshot']
    assert snapshot['kind']==kind and validate_snapshot(snapshot)==snapshot
    assert context['user_id'] is None and not context['grants']
    assert '攻略' in snapshot['next_command']
    assert list(asset_requests(snapshot))

def test_guide_display_still_rejects_private_fields_and_arbitrary_keys():
    _,snapshot=reply('wuthering_waves','散华',datetime.fromisoformat('2026-10-18T00:00:00+08:00'))
    snapshot['display_data']['guide']['user_id']='private'
    with pytest.raises(RenderingUnavailable):validate_snapshot(snapshot)

@pytest.mark.parametrize('game,text',[
    (None,'请发送「鸣潮 攻略 角色名」或「异环 攻略 角色名」查看单个角色攻略；可用角色见网站攻略页。'),
    ('wuthering_waves','请发送「鸣潮 攻略 角色名」查看单个角色攻略；可用角色见网站攻略页。'),
    ('nte','请发送「异环 攻略 角色名」查看单个角色攻略；可用角色见网站攻略页。'),
    ('endfield','当前项目尚未收录可核验的终末地角色攻略。'),
])
def test_bare_guide_is_a_text_notice_instead_of_an_index_image(game,text):
    from game_assistant.qq.cards import card_to_text
    card,snapshot=reply(game,None,datetime.fromisoformat('2026-10-18T00:00:00+08:00'))
    assert snapshot['kind']=='notice' and validate_snapshot(snapshot)==snapshot
    assert snapshot['display_data']['sections']==[] and snapshot['display_data']['notices']==[text]
    assert text in card_to_text(card)
    index={**snapshot,'kind':'guide_index','display_data':{'guides':[]}}
    with pytest.raises(RenderingUnavailable):validate_snapshot(index)

def test_missing_sources_are_explicit():
    card,missing=reply('endfield','伊冯',datetime.fromisoformat('2026-10-18T00:00:00+08:00'))
    assert missing['kind']=='notice' and '尚未收录' in str(card)

def test_guide_missing_source_version_stays_null_instead_of_vnone():
    now=datetime.fromisoformat('2026-10-18T00:00:00+08:00')
    _,snapshot=reply('wuthering_waves','赞妮',now)
    sources=snapshot['display_data']['guide']['sources']
    assert [source['version'] for source in sources]==['3.2',None]
    assert 'None' not in json.dumps(snapshot,ensure_ascii=False)
