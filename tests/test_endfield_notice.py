"""终末地公告解析。样本摘自官方公告原文（标题、时间行与少量说明行）：
「雪凇幽梦」「新潮起，故渊离」版本更新说明（官网/TapTap）、「春晓时」版本更新说明（B站 opus）、
「春晓时」版本更新维护预告（官网 news/2666）、「晨星于此闪耀」特许寻访说明（官网 news/1165）。
「寻遗散记」维护预告按「春晓时」预告的格式改写，只用来检验补全结束时间。
"""
from datetime import datetime, timezone

from game_assistant.sources.bilibili import classify_dynamic
from game_assistant.sources.public_content import calendar_from_posts, parse_post_events

XUESONG = """「雪凇幽梦」版本更新说明
亲爱的管理员：
▼//更新维护及补偿说明
■ 更新维护时间
2026/09/02 06:00 - 2026/09/02 12:00（UTC+8）
■ 更新维护及问题修复补偿说明
· 发放时间：2026/09/02更新维护后 - 下次版本更新维护前
▼//版本全新内容
■ 全新剧情
1. 探索任务
「据点建设·盈天台建设站·其三」「悬崖下的靶场」「钟鸣人归」
■ 全新寻访及申领
1.「冬猎」特许寻访
· 开放时间：「雪凇幽梦」版本更新后 - 2026/09/30 11:59（服务器时间）
· 寻访说明：「冬猎」特许寻访中，6星干员【提弗洛斯】获取概率提升，全部可能出现的6星干员包括：提弗洛斯/梨诺/诀/余烬/黎风/艾尔黛拉/别礼/骏卫。
2.「幽寒申领」
· 开放时间：「雪凇幽梦」版本更新后开启，于3次「特许寻访」后结束（从「冬猎」起计算）
· 申领说明：「幽寒申领」中，概率提升的6星武器为【寒夜幽影（施术单元）】。
3.「绚丽异彩」重构寻访#1
· 开放时间：2026/09/24 12:00（服务器时间） - 版本更新维护前
· 寻访说明：「绚丽异彩」重构寻访#1中，6星干员【伊冯】获取概率提升。
4.「点绘申领」重构申领#1
· 开放时间：2026/09/24 12:00（服务器时间） - 版本更新维护前
■ 全新活动
1.「雾隐冬梦深林中」叙事活动
· 活动时间：「雪凇幽梦」版本期间
2.「雪降深林」引入活动
· 活动时间：「雪凇幽梦」版本更新后 - 2026/09/30 12:00（服务器时间）
3.「挽弓试炼」挑战活动
· 活动时间：2026/09/09 12:00（服务器时间） - 版本更新维护前
4.「集成援助·泡泡出击」集成生产活动
· 活动时间：2026/09/16 12:00 - 2026/09/30 16:00（服务器时间）
· 物资兑换处开放时间：2026/09/16 12:00 - 2026/10/07 04:00（服务器时间）
5.「理智补给」限时活动
· 活动时间：
2026/09/17 04:00 - 2026/09/24 04:00（服务器时间）
2026/10/08 04:00 - 2026/10/15 04:00（服务器时间）
· 活动说明：活动期间，每日完成指定任务即可获得理智补给奖励。
6.「我们的大菲林！来袭！」馈赠活动
· 活动时间：2026/09/24 12:00（服务器时间） - 版本更新维护前
7.「于钟鸣的旧城」引入活动
· 活动时间：2026/09/24 12:00（服务器时间） - 版本更新维护前
8.「陵水渡秋」限时签到
· 活动时间：2026/10/01 12:00（服务器时间） - 版本更新维护前
9.「跑者运动会」趣味活动
· 活动时间：2026/10/01 12:00（服务器时间） - 版本更新维护前
10.「融合！山团团！」趣味活动
· 活动时间：2026/10/01 12:00（服务器时间） - 版本更新维护前
· 活动说明：前往网页活动，通过融合山团团获取积分。
■ 活动及玩法更新
1.「战争回响」常驻挑战玩法更新
○「虚像赛季」
· 赛季更新：「雪凇幽梦」版本更新后 - 2026/09/24 11:59（服务器时间）
○「错视赛季」
· 赛季更新：2026/09/24 12:00（服务器时间） - 版本更新维护前
2.「影拓丰碑」挑战玩法更新，开放「幽影刻形」系列关卡
· 开放时间：2026/10/05 12:00（服务器时间）
同时，玩法更新后还将同步开放「丰碑留名·刻影」限时挑战活动
· 活动时间：2026/10/05 12:00 - 2026/10/19 04:00（服务器时间）
▼//优化
1.「选剑演武」相关优化
· 活动时间：2026/09/02 12:00 - 2026/09/03 12:00（服务器时间）"""

CHUNXIAO = """「春晓时」版本更新说明
■ 更新维护时间
2026/04/17 06:00 - 2026/04/17 12:00（UTC+8）
■ 全新寻访及申领
1.「春雷动，万物生」特许寻访
· 开放时间：「春晓时」版本开启后 - 2026/05/22 11:59（服务器时间）
2. 「行舟申领」开放
· 开放时间：「春晓时」版本更新后开启，于3次「特许寻访」后结束（从「春雷动，万物生」起计算）
3.「辉光庆典」特殊寻访
· 开放时间：2026/05/14 12:00（服务器时间） - 版本更新维护前
4.「熔灼申领」开放
· 开放时间：2026/05/14 12:00（服务器时间）开启，于「辉光庆典」特殊寻访后结束
■ 全新活动
2.「干员培养助力」新手活动
· 活动时间：「春晓时」版本开启后常驻开放
7.「集成援助·掌中救星」集成生产活动
· 活动开放时间：2026/04/28 12:00 - 2026/05/13 16:00（服务器时间）"""

CHUNXIAO_NOTICE = """「春晓时」版本更新维护预告
亲爱的管理员：
《明日方舟：终末地》计划将于2026年4月17日 06:00（UTC+8）开始对游戏客户端进行版本更新停机维护，维护完成后将更新至全新版本「春晓时」。
▼//维护时间
2026/04/17 06:00 - 2026/04/17 12:00（UTC+8）"""

NEXT_NOTICE = """「寻遗散记」版本更新维护预告
《明日方舟：终末地》计划将于2026年6月5日 06:00（UTC+8）开始对游戏客户端进行版本更新停机维护，维护完成后将更新至全新版本「寻遗散记」。"""

MORNING_STAR = """「晨星于此闪耀」特许寻访说明
▼//「晨星于此闪耀」特许寻访说明
· 开放时间：2026/08/09 12:00（服务器时间） - 版本更新维护前
· 开放条件：完成主线任务「第一章 - 进程Ⅰ - 基地解围」
· 「晨星于此闪耀」特许寻访中，概率提升的6星干员为【梨诺】。
▼//「特许寻访」奖励
在「晨星于此闪耀」特许寻访中，累计达到指定寻访次数，即可获得对应奖励。"""

XIANGYUAN = """「向渊行」版本更新说明
■ 更新维护时间
2026/07/16 06:00 - 2026/07/16 12:00（UTC+8）
■ 全新寻访及申领
1.「临渊望北」特许寻访
· 开放时间：「向渊行」版本开启后 - 2026/08/09 11:59（服务器时间）"""

OLD_BANNER = """「逐罪者」特许寻访说明
▼//「逐罪者」特许寻访说明
· 开放时间：2026/06/26 12:00（服务器时间） - 版本更新维护前"""


def post(body, id, published):
    return dict(id=id, title=body.splitlines()[0], body=body, decision='accepted', published_at=published,
                fetched_at=published, source='bilibili', source_name='B站官方动态', url='https://t.bilibili.com/' + id)


def by_name(events):
    return {(e['name'], e.get('phase')): e for e in events}


def test_version_notes_cover_banners_relative_ends_phases_and_sub_items():
    calendar = calendar_from_posts([post(XUESONG, '1', '2026-09-02T04:00:00+00:00')], 'endfield',
                                   datetime(2026, 9, 25, tzinfo=timezone.utc))
    assert calendar['version'] == '雪凇幽梦' and calendar['source_post_id'] == '1'
    events = by_name(calendar['events'])
    assert len(events) == 19
    winter = events[('冬猎', None)]
    assert (winter['category'], winter['start_at'], winter['start_date']) == ('角色寻访', None, '2026-09-02')
    assert (winter['start_precision'], winter['end_at']) == ('relative', '2026-09-30T11:59:00+08:00')
    assert winter['aliases'] == ['冬猎', '提弗洛斯']
    weapon = events[('幽寒申领', None)]
    assert (weapon['category'], weapon['end_at'], weapon['end_precision']) == ('武器申领', None, 'dependent')
    assert weapon['end_text'] == '于3次「特许寻访」后结束'
    assert '从「冬猎」起计算' in weapon['time_text']
    rerun = events[('绚丽异彩', None)]
    assert (rerun['start_at'], rerun['end_at'], rerun['end_text']) == ('2026-09-24T12:00:00+08:00', None, '版本更新维护前')
    story = events[('雾隐冬梦深林中', None)]
    assert (story['start_precision'], story['start_date'], story['end_precision']) == ('relative', '2026-09-02', 'version_end')
    assert events[('陵水渡秋', None)]['category'] == '签到活动'
    assert events[('集成援助·泡泡出击·物资兑换处', None)]['end_at'] == '2026-10-07T04:00:00+08:00'
    assert [events[('理智补给', n)]['start_at'] for n in (1, 2)] == ['2026-09-17T04:00:00+08:00', '2026-10-08T04:00:00+08:00']
    assert events[('战争回响·虚像赛季', None)]['category'] == '玩法更新'
    assert events[('丰碑留名·刻影', None)]['end_at'] == '2026-10-19T04:00:00+08:00'
    assert ('影拓丰碑', None) not in events  # 只有开放时刻的常驻内容不进日历
    assert ('选剑演武', None) not in events  # “▼//优化”之后的内容不解析


def test_next_version_notice_fills_version_end_times():
    notes = post(CHUNXIAO, '1', '2026-04-17T04:00:00+00:00')
    notice = post(NEXT_NOTICE, '2', '2026-06-01T04:00:00+00:00')
    before = by_name(calendar_from_posts([notes], 'endfield', datetime(2026, 5, 20, tzinfo=timezone.utc))['events'])
    assert before[('辉光庆典', None)]['end_at'] is None
    after = by_name(calendar_from_posts([notice, notes], 'endfield', datetime(2026, 6, 2, tzinfo=timezone.utc))['events'])
    assert after[('辉光庆典', None)]['end_at'] == '2026-06-05T06:00:00+08:00'
    assert after[('辉光庆典', None)]['end_text'] == '版本更新维护前'
    assert after[('熔灼申领', None)]['end_at'] is None  # 依附其他寻访的结束时间不推算
    assert after[('熔灼申领', None)]['end_text'] == '于「辉光庆典」特殊寻访后结束'
    assert ('干员培养助力', None) not in after  # 常驻
    assert after[('集成援助·掌中救星', None)]['start_at'] == '2026-04-28T12:00:00+08:00'
    assert after[('春雷动，万物生', None)]['start_date'] == '2026-04-17'


def test_future_version_notes_do_not_replace_the_current_version():
    current = post(CHUNXIAO, '1', '2026-04-17T04:00:00+00:00')
    future = post(XUESONG, '2', '2026-09-02T04:00:00+00:00')
    assert calendar_from_posts([future, current], 'endfield', datetime(2026, 5, 1, tzinfo=timezone.utc))['version'] == '春晓时'


def test_own_maintenance_notice_does_not_end_its_own_version():
    notes = post(CHUNXIAO, '1', '2026-04-17T04:00:00+00:00')
    notice = post(CHUNXIAO_NOTICE, '2', '2026-04-13T07:00:00+00:00')
    events = by_name(calendar_from_posts([notice, notes], 'endfield', datetime(2026, 5, 1, tzinfo=timezone.utc))['events'])
    assert events[('辉光庆典', None)]['end_at'] is None


def test_standalone_banner_notices_join_their_version_only():
    base = post(XIANGYUAN, '1', '2026-07-16T04:00:00+00:00')
    current = post(MORNING_STAR, '2', '2026-08-08T04:00:00+00:00')
    stale = post(OLD_BANNER, '3', '2026-06-25T04:00:00+00:00')
    events = by_name(calendar_from_posts([stale, current, base], 'endfield', datetime(2026, 8, 20, tzinfo=timezone.utc))['events'])
    assert set(events) == {('临渊望北', None), ('晨星于此闪耀', None)}
    morning = events[('晨星于此闪耀', None)]
    assert (morning['category'], morning['aliases'], morning['end_precision']) == ('角色寻访', ['晨星于此闪耀', '梨诺'], 'version_end')


def test_other_games_and_excluded_posts_are_unchanged():
    notes = post(XUESONG, '1', '2026-09-02T04:00:00+00:00')
    assert parse_post_events(notes, 'nte', '1.3') == []
    assert parse_post_events({**notes, 'decision': 'excluded'}, 'endfield', '雪凇幽梦') == []


def test_phases_joined_by_ji_are_separate_events():
    body = ("「新潮起，故渊离」版本更新说明\n■ 更新维护时间\n2026/03/12 06:00 - 2026/03/12 12:00（UTC+8）\n■ 全新活动\n"
            "7.「理智减耗」减耗活动\n· 活动时间：2026/03/22 12:00 - 2026/03/29 04:00 及 2026/04/10 12:00 - 2026/04/17 04:00（服务器时间）")
    events = parse_post_events(post(body, '1', '2026-03-12T04:00:00+00:00'), 'endfield', '新潮起，故渊离')
    assert [(e['phase'], e['end_at']) for e in events] == [(1, '2026-03-29T04:00:00+08:00'), (2, '2026-04-17T04:00:00+08:00')]


def dynamic(text, id='9'):
    return {'id_str': id, 'type': 'DYNAMIC_TYPE_WORD', 'modules': {
        'module_author': {'mid': 1265652806, 'name': '明日方舟终末地', 'pub_ts': 1788321600},
        'module_dynamic': {'desc': {'text': text}}}}


def test_bilibili_keeps_endfield_notices_that_mention_web_events():
    now = datetime(2026, 9, 3, tzinfo=timezone.utc)
    assert classify_dynamic(dynamic(XUESONG), '1265652806', now)['decision'] == 'accepted'
    assert classify_dynamic(dynamic(MORNING_STAR), '1265652806', now)['decision'] == 'accepted'
    promotion = classify_dynamic(dynamic('「山团团」网页活动开启！\n活动时间：2026/10/01 12:00 - 2026/10/14 23:59'), '1265652806', now)
    assert (promotion['decision'], promotion['reason'], promotion['rule_version']) == ('excluded', 'promotion', 5)
