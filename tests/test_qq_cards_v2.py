from PIL import Image
from io import BytesIO

import pytest

from game_assistant.qq.cards import card_to_text, validate_card_document
from game_assistant.qq.rendering import RenderingUnavailable

REF = 'qqasset_'+'a'*64


def card(count=40):
    return dict(version=2,kind='list',game='wuthering_waves',title='鸣潮 · 角色档案',
        subtitle='本人默认角色',sections=[dict(title='角色缓存',layout='grid',rows=[
            dict(title='合成测试角色完整长图 '+str(i),image=REF,fields=[dict(label='等级',value='90'),
                dict(label='共鸣链',value='0'),dict(label='属性',value='凝')]) for i in range(count)])],
        notices=['缓存装备不代表完整库存'],footer='更新：2026-10-14 20:30')


def test_v2_keeps_sixty_roles_without_page_or_1800_character_truncation():
    normalized=validate_card_document(card(60))
    assert len(normalized['sections'][0]['rows'])==60 and 'page' not in normalized
    text=card_to_text(normalized)
    assert len(text)<=1800 and '文字摘要' in text and '图片或网站' in text
    assert '更新：2026-10-14 20:30' in text and '缓存装备不代表完整库存' in text


@pytest.mark.parametrize('mutate',[
    lambda c:c.update(image='https://untrusted.test/image'),
    lambda c:c['sections'][0].update(layout='html'),
    lambda c:c['sections'][0]['rows'][0].update(image='C:/private/image.png'),
    lambda c:c['sections'][0]['rows'][0]['fields'][0].update(metric=dict(current=True,maximum=10)),
    lambda c:c['sections'][0]['rows'][0]['fields'][0].update(metric=dict(current=0,maximum=float('inf'))),
    lambda c:c['sections'][0]['rows'][0]['fields'][0].update(metric=dict(current=10**1000,maximum=10)),
    lambda c:c.update(sections=[dict(fields=[dict(label='x',value='x')]*48)]*8),
    lambda c:c['sections'][0].update(rows=[dict(title='x')]*257),
])
def test_v2_rejects_urls_paths_bad_metrics_and_document_budgets(mutate):
    value=card(1); mutate(value)
    with pytest.raises(ValueError):validate_card_document(value)


def test_v2_raw_unknown_metric_stays_unknown_and_real_zero_is_accepted():
    value=card(1)
    value['sections'][0]['fields']=[dict(label='体力',value='未知 / 240',metric=dict(current=None,maximum=240)),
        dict(label='探索',value='0 / 100',metric=dict(current=0,maximum=100))]
    fields=validate_card_document(value)['sections'][0]['fields']
    assert fields[0]['metric']['current'] is None and fields[1]['metric']['current']==0


def test_bounded_jpeg_fallback_preserves_browser_screenshot_dimensions():
    from game_assistant.qq.rendering import encode_image
    image = Image.effect_noise((960, 2800), 35).convert('RGB')
    output = BytesIO()
    image.save(output, format='PNG')
    png = output.getvalue()
    data = encode_image(png, max_bytes=1048576)
    assert data.startswith(b'\xff\xd8') and len(data) <= 1048576
    assert Image.open(BytesIO(data)).size == (960, 2800)
    with pytest.raises(RenderingUnavailable, match='size_limit'):
        encode_image(png, max_bytes=100)


@pytest.mark.parametrize('kind', ['overview', 'summary'])
def test_source_metadata_text_keeps_both_minute_timestamps_and_unknown_completeness(kind):
    value = dict(version=2, kind=kind, game='nte', title='异环', sections=[dict(title='账号', layout='stats', fields=[
        dict(label='等级', value='42'), dict(label='体力', value='180 / 240'),
        dict(label='更新时间', value='2026-10-14 08:00'), dict(label='体力更新时间', value='2026-10-14 08:01'),
        dict(label='数据状态', value='缓存快照'), dict(label='完整性', value='未知')])])
    text = card_to_text(value)
    assert '2026-10-14 08:00' in text and '2026-10-14 08:01' in text
    assert '完整性：未知' in text and '数据状态：缓存快照' in text


def test_plain_numeric_stat_preserves_unknown_maximum():
    value = dict(version=2, game='nte', kind='summary', title='账号', sections=[dict(layout='stats', fields=[
        dict(label='等级', value='60', metric=dict(current=60, maximum=None))])])
    field = validate_card_document(value)['sections'][0]['fields'][0]
    assert field['metric'] == {'current': 60, 'maximum': None}
    assert '等级：60' in card_to_text(value)
