
import pytest

from game_assistant.qq.cards import validate_card_document, card_to_text


def calendar():
    return dict(version=3, kind='calendar', game='all', title='合成活动日历',
        timeline=dict(start='2026-10-01', end='2026-11-01', today='2026-10-14', timezone='Asia/Shanghai'),
        sections=[dict(title='鸣潮 · 活动', game='wuthering_waves', category='活动', layout='timeline', rows=[
            dict(title='跨月活动完整长名称', fields=[dict(label='时间',value='2026-09-28 10:00 至 2026-10-21 12:00'),
                dict(label='来源',value='游戏官网 · 合成公告')], timeline=dict(start='2026-09-28',end='2026-10-22',
                precision='minute',continues_before=True,continues_after=False)),
            dict(title='日期待确认',fields=[dict(label='时间',value='版本更新后')])])])


def test_v3_calendar_preserves_axis_precision_and_unknown_boundaries():
    source=calendar()
    normalized=validate_card_document(source)
    assert normalized['timeline']==source['timeline']
    assert 'timeline' not in normalized['sections'][0]['rows'][1]
    assert '版本更新后' in card_to_text(normalized)
    assert '游戏官网 · 合成公告' in card_to_text(normalized)
    assert '2026-09-28 10:00 至 2026-10-21 12:00' in card_to_text(normalized)
    assert source==calendar()


@pytest.mark.parametrize('mutation',[
    lambda c:c['timeline'].update(end='2026-10-01'),
    lambda c:c['timeline'].update(start='2026-02-30'),
    lambda c:c['timeline'].update(timezone='UTC'),
    lambda c:c['sections'][0]['rows'][0]['timeline'].update(precision='unknown'),
    lambda c:c['sections'][0]['rows'][0]['timeline'].update(continues_before=1),
    lambda c:c['sections'][0].update(game='arbitrary'),
])
def test_v3_rejects_unbounded_or_invented_timeline(mutation):
    value=calendar();mutation(value)
    with pytest.raises(ValueError):validate_card_document(value)


def gacha():
    return dict(version=3,kind='summary',game='nte',title='全卡池抽卡',sections=[dict(title='角色池',layout='gacha',rows=[
        dict(title='合成角色',fields=[dict(label='获取时间',value='2026-10-14 10:00')],gacha=dict(
            draws=63,guarantee=80,lucky_type=1,color='green',lucky_text='上游评价')),
        dict(title='未知保底',gacha=dict(draws=10,guarantee=None,lucky_type=0,color='yellow',lucky_text=''))])])


def test_v3_gacha_keeps_upstream_colors_and_unknown_guarantee():
    rows = validate_card_document(gacha())['sections'][0]['rows']
    assert rows[0]['gacha']['color'] == 'green' and rows[0]['gacha']['guarantee'] == 80
    assert rows[1]['gacha']['guarantee'] is None
    assert rows[0]['gacha']['lucky_text'] == '上游评价'
    text = card_to_text(gacha())
    assert '上游评价' in text and '2026-10-14 10:00' in text


@pytest.mark.parametrize('change',[
    dict(draws=True),dict(guarantee=-1),dict(color='#04c8a3'),dict(lucky_type=0,color='green'),
    dict(lucky_type=0,color='yellow',lucky_text='伪造评价'),dict(draws=10**1000),
])
def test_v3_gacha_rejects_invalid_semantics(change):
    value=gacha();value['sections'][0]['rows'][0]['gacha'].update(change)
    with pytest.raises(ValueError):validate_card_document(value)


def test_v3_section_tone_preserves_top_level_upstream_luck_without_row_semantics():
    value = gacha()
    value['sections'].insert(0, dict(title='社区统计', layout='stats', tone='red', fields=[dict(label='塔吉多近期评价', value='合成上游评价')]))
    assert validate_card_document(value)['sections'][0]['tone'] == 'red'
    assert '合成上游评价' in card_to_text(value)
    value['sections'][0]['tone'] = '#e55961'
    with pytest.raises(ValueError):
        validate_card_document(value)


def test_v3_equipment_refs_are_validated_and_names_survive_text_fallback():
    from game_assistant.qq.cards import image_references
    ref = 'qqasset_' + 'b' * 64
    value = dict(version=3, kind='overview', game='all', title='配装速览', sections=[dict(title='鸣潮', layout='equipment', rows=[
        dict(title='合成角色', equipment=[dict(title='真实采集武器', subtitle='Lv.90', image=ref)])])])
    normalized = validate_card_document(value)
    assert image_references(normalized) == (ref,)
    assert '真实采集武器' in card_to_text(normalized)
    value['sections'][0]['rows'][0]['equipment'][0]['image'] = 'C:/private.png'
    with pytest.raises(ValueError):
        validate_card_document(value)


def test_v3_overview_equipment_avoids_duplicate_names_and_keeps_counts_and_missing_states():
    from game_assistant.qq.presentation import overview_roles
    from game_assistant.accounts.models import QueryResult
    nte=overview_roles('nte','tajiduo',QueryResult({'entries':[dict(name='合成角色',level=80,weapon=dict(name='已采集弧盘',level=60),
        equipment=[dict(name='已采集装备',slot='槽位',level=25)]),dict(name='缺失角色',level=70)]},None,'ok',None))
    row=nte[0]['rows'][0]
    assert [item['title'] for item in row['equipment']]==['已采集弧盘','已采集装备']
    assert row['fields']==[] and row['subtitle']=='等级 80'
    assert nte[0]['rows'][1]['fields']==[dict(label='装备',value='未采集')]
    ww=overview_roles('wuthering_waves','kuro',QueryResult([dict(role_id=1,name='合成共鸣者',level=90)],None,'ok',None),
        details={'1':{'weapon_data':{'level':90,'weapon':{'weapon_name':'真实武器'}},'phantom_data':{'equip_phantom_list':[
            dict(level=25,phantom_prop={'name':'真实声骸'})]}}})
    assert [item['label'] for item in ww[0]['rows'][0]['fields']]==['已采集声骸']


def test_v3_overview_scope_notice_survives_text_fallback():
    value = dict(version=3, kind='overview', game='all', title='总览', sections=[dict(title='角色配装', layout='equipment', fields=[
        dict(label='范围', value='仅已采集配装；完整角色请发送「鸣潮 角色」')], rows=[dict(title='角色')])])
    assert '范围：仅已采集配装；完整角色请发送「鸣潮 角色」' in card_to_text(value)
