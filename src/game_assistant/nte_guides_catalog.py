"""Reviewed community advice and original-image indexes; never inferred account builds."""
from copy import deepcopy

REVIEWED_AT = '2026-09-26'
SECTIONS = {'weapons': '弧盘推荐', 'teams': '配队推荐', 'sets': '卡带配装', 'stats': '卡带词条', 'skills': '技能加点'}
SOURCES = {
    495234: {'id': 495234, 'title': '异环角色 | V1.4黑羽培养攻略一图流', 'author': '轩儿Zero', 'version': '1.4',
             'fingerprint': '4d1530c13f7ba6a2f92a9b295fe7f0e94e32c625482adccf4c52dda11591edb6'},
    491439: {'id': 491439, 'title': '异环V1.3全角色养成一图流', 'author': '轩儿Zero', 'version': '1.3',
             'fingerprint': '15a1ac68523ab110d1683a6e0ffe43548e9ba26c9efd8a500103ef94caeab9db'},
}
for _source in SOURCES.values():
    _source['url'] = f"https://www.tajiduo.com/bbs/index.html#/post?postId={_source['id']}&id=2"

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


def guide_catalog():
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
    return deepcopy({'reviewed_at': REVIEWED_AT, 'guides': guides, 'sources': list(SOURCES.values())})
