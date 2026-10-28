"""Reviewed community advice and original-image indexes; never inferred account builds."""
from copy import deepcopy
import re

REVIEWED_AT = '2026-09-26'
SECTIONS = {'weapons': '弧盘推荐', 'teams': '配队推荐', 'sets': '卡带配装', 'stats': '卡带词条', 'skills': '技能加点'}
SOURCES = {
    495234: {'id': 495234, 'title': '异环角色 | V1.4黑羽培养攻略一图流', 'author': '轩儿Zero', 'version': '1.4',
             'fingerprint': '4d1530c13f7ba6a2f92a9b295fe7f0e94e32c625482adccf4c52dda11591edb6'},
    491439: {'id': 491439, 'title': '异环V1.3全角色养成一图流', 'author': '轩儿Zero', 'version': '1.3',
             'fingerprint': '15a1ac68523ab110d1683a6e0ffe43548e9ba26c9efd8a500103ef94caeab9db'},
}


def post_url(post_id):
    return f"https://www.tajiduo.com/bbs/index.html#/post?postId={post_id}&id=2"


for _source in SOURCES.values():
    _source['url'] = post_url(_source['id'])

# Both catalog sources are 轩儿Zero's: the daily job lists that author's posts (one anonymous
# request) and reports guides newer than the catalog's. Titles follow the author's own patterns.
AUTHOR = {'uid': 10208854, 'name': '轩儿Zero'}
ROLE_POST = re.compile(r'^异环角色\s*[|｜]\s*V(\d+(?:\.\d+)*)\s*(\S+?)培养攻略一图流$')
ALL_POST = re.compile(r'^异环V(\d+(?:\.\d+)*)全角色养成一图流$')

# The page index is checked against the six original images, not guessed from a search title.
PAGES = [
    [('灵可', '灵', '副 C'), ('伊洛伊', '灵', '辅助'), ('九原', '灵', '副 C'), ('薄荷', '灵', '主 C')],
    [('娜娜莉', '灵', '主 C'), ('残虹', '咒', '主 C'), ('阿德勒', '咒', '辅助'), ('白藏', '咒', '主 C')],
    [('早雾', '咒', '辅助'), ('真红', '光', '主 C'), ('小吱', '光', '主 C'), ('埃德嘉', '光', '辅助')],
    [('浔', '光', '副 C'), ('主角·零', '光', '副 C'), ('卡厄斯', '相', '主 C'), ('翳', '相', '主 C')],
    [('哈索尔', '相', '副 C'), ('安魂曲', '暗', '主 C'), ('达芙蒂尔', '暗', '副 C'), ('海月', '魂', '主 C')],
    [('哈尼娅', '魂', '辅助'), ('法帝娅', '魂', '辅助')],
]


def section(key, pages, *items, note=''):
    return {'key': key, 'title': SECTIONS[key], 'items': list(items), 'pages': pages, 'note': note}


REVIEWED = {
    '黑羽': [
        section('weapons', [4], '输出路线优先「罪与罚」；其他 S 级备选有「噬心诡刃」「好狗狗走四方」。',
                'A级可考虑「光波眩晕」「当心头顶」；「思考喵」也是备选。辅助用途优先考虑队伍收益。',
                note='正文未给出所有替代弧盘的统一强度排序，以上不代表完整排名。'),
        section('teams', [5], '主 C：搭配相属性、暗属性成员，再补一名增益辅助。',
                '副 C：作者列举安魂曲／残虹队、卡厄斯队作为方向。', note='保留配队方向，不把属性位置擅自替换成固定角色；具体示例见原图。'),
        section('sets', [2], '主 C／副 C：恶魔之血·诅咒。', '0 觉纯辅助：可选音速蓝刺猬。',
                note='驱动块形状和拼放位置见第 2 张原图；不能将不同定位的配装直接混用。'),
        section('stats', [2], '使用提供暴击率的专武时，优先考虑暴击伤害或魂属性伤害增强主词条。',
                '当心头顶／思考喵方案可考虑暴击率主词条；须结合实际面板。',
                '副词条：暴击率≈暴击伤害，其后是伤害增加、攻击力百分比、环合强度。'),
        section('skills', [3], '极轨终结、变轨技能、普通攻击同属优先投入项，均先于援护技。',
                note='正文强调资源有限时按输出手法取舍，不强行给三个主要技能排唯一顺序。'),
    ],
    '残虹': [
        section('weapons', [2], '优先「噬心诡刃」，之后是「灵敏之绵」；替代项有「当心头顶」「思考喵」。'),
        section('teams', [2], '示例一：残虹、灵可、早雾、伊洛伊。', '示例二：安魂曲、残虹、灵可、早雾。', note='这是 V1.3 原图的阵容示例，不含后续版本角色调整。'),
        section('sets', [2], '主 C 使用真红·双生蝶；副 C 方案使用失落光芒。', note='两种定位分别配置，驱动块布局见原图第 2 页。'),
        section('stats', [2], '专武方案侧重咒属性伤害主词条；非专武方案考虑暴击率。', '副词条先补双暴，其后是伤害增加和攻击力百分比。'),
        section('skills', [2], '普通攻击 = 极轨终结 = 变轨技能 > 援护技。', '被动 2 优先于被动 1。'),
    ],
    '灵可': [
        section('weapons', [1], '优先「远行者之声」；其后依次参考「不屈之绵」「预备备」「鲸之歌」。'),
        section('teams', [1], '示例一：残虹、灵可、早雾、伊洛伊。', '示例二：安魂曲、残虹、灵可、早雾。'),
        section('sets', [1], '副 C 方案使用森林萤火之心，作者未列次选套装。', note='驱动块类型与拼放位置以第 1 页原图为准。'),
        section('stats', [1], '主词条考虑灵属性伤害或暴击伤害。', '副词条：双暴优先，其后为伤害增加、攻击力百分比。'),
        section('skills', [1], '援护技优先，其后依次为极轨终结、变轨技能、普通攻击。', '两个被动按相同优先级处理。'),
    ],
    '伊洛伊': [
        section('weapons', [1], '优先「错误的门」；其后依次参考「漆黑青春妄想」「极速之绵」「开始净空」。'),
        section('teams', [1], '示例一：娜娜莉、主角·零、九原、伊洛伊。', '示例二：真红、哈索尔、主角·零、伊洛伊。'),
        section('sets', [1], '辅助定位首选音速蓝刺猬，次选森林萤火之心。', note='两套驱动块布局见第 1 页原图。'),
        section('stats', [1], '辅助主词条可围绕攻击力百分比、治疗增益或暴击率选择。', '副词条兼顾攻击力；若追求输出，再优先双暴和伤害增加。', note='输出词条的优先级带有“如想输出”的前提，不是所有辅助玩法都要堆双暴。'),
        section('skills', [1], '极轨终结、变轨技能、普通攻击同优先级，先于援护技。', '两个被动按相同优先级处理。'),
    ],
    '娜娜莉': [
        section('weapons', [2], '优先「预备备」，其次「不屈之绵」；之后参考「焰魂狂飙」或「欧拉欧拉！」，也可考虑「鲸之歌」。'),
        section('teams', [2], '示例一：娜娜莉、九原、伊洛伊、主角·零。', '示例二：娜娜莉、九原、主角·零、阿德勒。'),
        section('sets', [2], '主 C 方案使用森林萤火之心，作者未列次选套装。', note='驱动块类型与完整拼放参考原图第 2 页。'),
        section('stats', [2], '主词条：灵属性伤害 > 暴击伤害 > 攻击力百分比 > 暴击率。', '副词条：双暴优先，其后伤害增加与攻击力百分比同级，再考虑攻击力。'),
        section('skills', [2], '普通攻击 > 极轨终结 > 变轨技能 > 援护技。', '被动 1 优先于被动 2。'),
    ],
}


# 2026-10-18 visual check of the six V1.3 originals from post 491439.
# Only readable recommendations are transcribed; avatar-only teams and block
# layouts remain original-image evidence, not guessed text advice.
PARTIAL_REVIEWED_AT = '2026-10-18'
PARTIAL = {
    '九原': ('现实避难所', '副 C 采用森林萤火之心；原图未列次选。', '主词条侧重暴击率，其后灵属性伤害、暴击伤害与攻击百分比。', '极轨终结优先，其后普通攻击、变轨技能、援护技。'),
    '薄荷': ('最后一朵玫瑰', '主 C 采用森林萤火之心；原图未列次选。', '主词条依次考虑灵属性伤害、暴击率、暴击伤害、攻击百分比。', '普通攻击优先，其后极轨终结、变轨技能、援护技。'),
    '阿德勒': ('勿忘伞', '辅助可用守卫王国，次选音速蓝刺猬。', '主词条优先防御百分比，其后倾陷；副词条依次考虑防御百分比、防御、倾陷。', '变轨技能优先，其后极轨终结、普通攻击、援护技。'),
    '白藏': ('茶花会', '主 C 采用真红·双生蝶；原图未列次选。', '主词条考虑咒属性伤害或暴击伤害，其后倾陷。', ''),
    '早雾': ('好狗狗走四方', '辅助采用音速蓝刺猬；原图未列次选。', '想补输出时考虑暴击率；倾陷与暴击伤害同级。副词条双暴仅限输出用途。', ''),
    '真红': ('穿过胭红蜃景', '主 C 采用失落光芒；原图未列次选。', '主词条优先暴击率；副词条依次考虑暴击率、暴击伤害、伤害增加和攻击。', ''),
    '小吱': ('思考喵', '主 C 采用失落光芒；原图未列次选。', '主词条为光属性伤害；副词条优先伤害增加，再考虑暴击伤害、暴击率和攻击百分比。', ''),
    '埃德嘉': ('扭曲之城的呼唤', '辅助首选缇娅的夜间酒馆，次选音速蓝刺猬。', '主词条依次考虑治疗增益、生命百分比、环合和倾陷。', ''),
    '浔': ('行进于时间之外', '副 C 采用失落光芒；原图未列次选。', '主词条依次考虑暴击率、光属性伤害、暴击伤害。', '极轨终结优先，其后变轨技能、援护技、普通攻击。'),
    '主角·零': ('倾世之雨', '副 C 用失落光芒；辅助用音速蓝刺猬，须按定位选择。', '主词条为环合；副词条优先环合，其后双暴，再考虑伤害增加与攻击百分比。', '变轨技能与极轨终结同级，其后援护技、普通攻击。'),
    '卡厄斯': ('众人追寻之物', '主 C 采用街头拳王；原图未列次选。', '主词条相属性伤害与攻击百分比近似同级，其后暴击伤害。', '普通攻击优先，其后极轨终结、变轨技能、援护技。'),
    '翳': ('好狗狗走四方', '主 C 采用街头拳王；原图未列次选。', '主词条依次考虑相属性伤害、暴击伤害、暴击率。', '极轨终结优先，其后普通攻击、变轨技能、援护技。'),
    '哈索尔': ('焰魂狂飙', '副 C 采用街头拳王；原图未列次选。', '主词条依次考虑相属性伤害、暴击伤害、暴击率。', ''),
    '安魂曲': ('最后一朵玫瑰', '主 C 采用迪亚波罗斯；原图未列次选。', '主词条先考虑暗属性伤害，再考虑暴击率；副词条优先双暴。', ''),
    '达芙蒂尔': ('漆黑青春妄想', '副 C 采用迪亚波罗斯；原图未列次选。', '主词条倾陷在 3、5 觉优先，与暴击率同级，其后暴击伤害；须结合觉醒等级。', ''),
    '海月': ('银河暂留', '主 C 采用恶魔之血·诅咒；原图未列次选。', '主词条先考虑暴击率，再考虑魂属性伤害；攻击百分比与暴击伤害同级。', ''),
    '哈尼娅': ('引爆全场', '辅助首选音速蓝刺猬，次选恶魔之血·诅咒。', '主词条倾陷与环合同级，先于魂属性伤害，其后双暴。', ''),
    '法帝娅': ('永恒圆舞曲', '辅助采用小小大冒险；副 C 采用静谧山庄，须按定位选择。', '主词条先考虑生命百分比，其后心灵伤害，再考虑魂属性伤害和双暴。', ''),
}


def partial_sections(guide):
    weapon, sets, stats, skills = PARTIAL[guide['name']]
    values = {'weapons': f'原图列在首位的弧盘为「{weapon}」。其余备选与适用条件请核对原图。',
              'sets': sets, 'stats': stats, 'skills': skills, 'teams': ''}
    result = []
    for key in SECTIONS:
        note = ('配队仅有角色头像，未逐一核实名字，不生成固定队伍。' if key == 'teams' else
                '原图文字尚未完整核对，保留原图页入口。' if not values[key] else
                '仅核对 V1.3 原图可读文字；完整备选、驱动块形状及新版本适用性须查看原图。')
        result.append(section(key, guide['pages'], *([values[key]] if values[key] else []), note=note))
    return result


def guide_catalog(discovered=()):
    """The reviewed catalog; ``discovered`` (GuideService.new_posts) adds newer original posts."""
    guides = [{'id': '黑羽', 'name': '黑羽', 'aliases': [], 'element': '魂', 'role': '主 C / 副 C / 辅助',
               'source_id': 495234, 'pages': [1, 2, 3, 4, 5]}]
    for page, rows in enumerate(PAGES, 1):
        for name, element, role in rows:
            guides.append({'id': name, 'name': name, 'aliases': ['零', '主角'] if name == '主角·零' else ['哈妮娅'] if name == '哈尼娅' else [],
                           'element': element, 'role': role, 'source_id': 491439, 'pages': [page]})
    for guide in guides:
        guide['status'] = 'reviewed' if guide['name'] in REVIEWED else 'original_only'
        guide['sections'] = REVIEWED.get(guide['name'], [section(key, guide['pages'], note='尚未整理文字推荐，可打开对应原图页查看。') for key in SECTIONS])
        guide['reviewed_at'] = REVIEWED_AT if guide['status'] == 'reviewed' else None
        if guide['name'] in PARTIAL:
            guide['sections'] = partial_sections(guide)
            guide['partial_reviewed_at'] = PARTIAL_REVIEWED_AT
            guide['gap_note'] = '已核对部分弧盘、卡带与词条文字；配队头像、完整技能或布局未全部核实，不标记为完整摘要。'
    sources = list(SOURCES.values())
    names = {name: g for g in guides for name in [g['name'], *g['aliases']]}
    for post in discovered:
        meta = {k: post[k] for k in ('id', 'title', 'author', 'version', 'url', 'published_at')}
        sources.append({**meta, 'discovered': True})
        if post['role'] is None:
            continue
        guide = names.get(post['role'])
        if guide is not None:
            # The summary stays the reviewed one; the page points at the newer original.
            guide['newer_source'] = meta
            continue
        pages = list(range(1, post['images'] + 1))
        guides.append({'id': post['role'], 'name': post['role'], 'aliases': [], 'element': None, 'role': None,
                       'source_id': post['id'], 'pages': pages, 'status': 'original_only', 'discovered': True,
                       'reviewed_at': None, 'sections': [section(key, pages, note='新帖原图尚未整理文字推荐，请查看原图。') for key in SECTIONS]})
    return deepcopy({'reviewed_at': REVIEWED_AT, 'guides': guides, 'sources': sources,
                     'new_posts': [dict(post) for post in discovered]})
