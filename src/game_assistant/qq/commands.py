"""Small explicit self-query grammar and QQ reply text sanitizing."""
from dataclasses import dataclass
import re

GAMES = {'ww':'wuthering_waves','鸣潮':'wuthering_waves','wuthering_waves':'wuthering_waves',
         'yh':'nte','异环':'nte','nte':'nte','终末地':'endfield','endfield':'endfield'}
GAME_NAMES = {'wuthering_waves':'鸣潮','nte':'异环','endfield':'终末地'}

VERBS = {'查询':'summary','query':'summary','总览':'summary','概览':'summary','summary':'summary',
         '角色':'roles','干员':'roles','roles':'roles','体力':'stamina','stamina':'stamina',
         '探索':'exploration','exploration':'exploration','挑战':'combat','战斗':'combat','combat':'combat',
         '进度':'progress','progress':'progress','抽卡':'gacha','寻访':'gacha','gacha':'gacha',
         '活动':'events','近期活动':'recent_events','events':'events','recent_events':'recent_events','日历':'calendar','calendar':'calendar','公告':'news','资讯':'news','news':'news',
         '刷新':'refresh','refresh':'refresh'}
VERBS.update({'帮助':'help','help':'help','数据坞':'calabash','calabash':'calabash','活动进度':'activities','activities':'activities',
              '资源':'resources','resources':'resources','房产':'realestate','realestate':'realestate',
              '车辆':'vehicles','vehicles':'vehicles','队伍':'teams','teams':'teams','档案':'record','record':'record'})
VERBS.update({'理智':'stamina','练度':'training','全员练度':'training','training':'training',
              '地区':'regions','地区建设':'regions','regions':'regions','帝江号':'ship','ship':'ship','寻访战报':'gacha',
              '光荣之路':'honor','勋章':'honor','奖章':'honor','honor':'honor'})
VERBS.update({'攻略':'guide','角色攻略':'guide','guide':'guide','guides':'guide'})
PAGED_COMMANDS = frozenset(('help','overview','summary','status','roles','exploration','combat','progress','gacha','calendar','events','recent_events',
                            'resources','realestate','vehicles','teams','ship','honor'))
MAX_PAGE = 100
ALL_GAMES = tuple(GAME_NAMES)
WW, NTE, EF = ('wuthering_waves',), ('nte',), ('endfield',)


@dataclass(frozen=True)
class Entry:
    """One help line and the (command, game) pairs it makes valid."""
    command: str
    section: str
    description: str
    syntax: str  # 游戏 is the game-prefix placeholder
    games: tuple = ()
    bare: bool = False  # also valid without a game


# The single source of valid commands: the parser rejects every pair missing
# here, and help lists exactly these lines.
REGISTRY = (
    Entry('binding','绑定与账号','绑定网站账号','绑定 实际绑定码',bare=True),
    Entry('status','绑定与账号','授权状态','我的账号',bare=True),
    Entry('dashboard','绑定与账号','网站入口','看板',bare=True),
    Entry('help','绑定与账号','单游戏帮助','游戏 帮助',ALL_GAMES,bare=True),
    Entry('overview','总览与角色','本人总览','我的总览',bare=True),
    Entry('summary','总览与角色','单游戏总览','游戏 总览',ALL_GAMES),
    Entry('roles','总览与角色','角色列表','游戏 角色',ALL_GAMES),
    Entry('roles','总览与角色','角色详情','游戏 角色 精确名称',ALL_GAMES),
    Entry('guide','总览与角色','角色攻略','游戏 攻略 精确名称',ALL_GAMES,bare=True),
    Entry('exploration','资源与进度','探索进度','游戏 探索',ALL_GAMES),
    Entry('progress','资源与进度','成长进度','游戏 进度',WW+NTE),
    Entry('refresh','资源与进度','刷新缓存','刷新 游戏',ALL_GAMES),
    Entry('gacha','抽卡','抽卡记录','游戏 抽卡',ALL_GAMES),
    Entry('recent_events','活动与日历','即将开始或结束的活动','游戏 近期活动',ALL_GAMES,bare=True),
    Entry('events','活动与日历','进行中的活动','游戏 活动',ALL_GAMES,bare=True),
    Entry('calendar','活动与日历','版本日历','游戏 日历',ALL_GAMES,bare=True),
    Entry('combat','鸣潮专项','挑战记录','游戏 挑战',WW),
    Entry('resources','鸣潮专项','资源收入','游戏 资源',WW),
    Entry('realestate','异环专项','房产','游戏 房产',NTE),
    Entry('vehicles','异环专项','车辆','游戏 车辆',NTE),
    Entry('teams','异环专项','官方配队','游戏 队伍',NTE),
    Entry('ship','终末地专项','帝江号','游戏 帝江号',EF),
    Entry('honor','终末地专项','光荣之路','游戏 光荣之路',EF),
    Entry('combat','终末地专项','挑战记录','游戏 挑战',EF),
    Entry('gacha','终末地专项','寻访战报','游戏 寻访战报',EF),
    Entry('roles','终末地专项','干员配装','游戏 干员 精确名称',EF),
)
ACCEPTED = frozenset((entry.command,game) for entry in REGISTRY for game in entry.games+((None,) if entry.bare else ()))

# Retired for one release cycle: the old words still parse, but only to a
# fixed notice that never reads account data or builds an old panel. Delete
# together with the 'retired' branches in query_routes.py and group_settings.py.
_TO_HELP = '该指令已下线，发送「帮助」查看现有指令。'
RETIRED = {  # command: (games it is retired for, None = all games and the bare word; reply)
    'news':(None,'该指令已下线，公告请到网站“公告资讯”页查看。'),
    'stamina':(None,_TO_HELP),'calabash':(None,_TO_HELP),'activities':(None,_TO_HELP),'record':(None,_TO_HELP),
    'training':(None,'该指令已下线，请改用「终末地 角色」。'),
    'regions':(None,'该指令已下线，请改用「终末地 探索」。'),
    'progress':(EF,_TO_HELP),'combat':(NTE,_TO_HELP),
}


def accepts(command, game=None):
    return (command,game) in ACCEPTED


def retired_reply(verb, game=None):
    games,reply=RETIRED.get(verb,((),None))
    return reply if games is None or game in games else None


@dataclass(frozen=True)
class Command:
    command: str
    game: str | None = None
    code: str | None = None
    role_name: str | None = None
    page: int = 1
    retired: str | None = None  # the retired verb, see RETIRED


def parse_command(content):
    if not isinstance(content, str) or len(content)>512:
        return Command('help')
    raw = re.sub(r'<@!?\d+>', '', content).strip().lstrip('/').strip()
    if any(ord(c)<32 and c not in ('\t','\n','\r') for c in raw):
        return Command('help')
    parts = raw.split()
    if len(parts)==2 and parts[0] in ('绑定','bind') and re.fullmatch(r'[A-Za-z0-9_-]{4,128}',parts[1]):
        return Command('binding',code=parts[1])
    if raw in ('帮助','help','?',''):
        return Command('help')
    if raw in ('我的账号','状态','status'):
        return Command('status')
    if raw in ('我的','总览','我的总览','overview','my'):
        return Command('overview')
    if len(parts)==2 and parts[0] in ('我的','总览','我的总览','overview','my','我的账号','状态','status'):
        if re.fullmatch(r'[0-9]+',parts[1]) and 1<=int(parts[1])<=MAX_PAGE:
            return Command('status' if parts[0] in ('我的账号','状态','status') else 'overview',page=int(parts[1]))
    if raw in ('看板','dashboard'):
        return Command('dashboard')
    if raw in GAMES:
        return Command('summary',GAMES[raw])
    if len(parts)==1 and parts[0] in VERBS and retired_reply(VERBS[parts[0]]):
        return Command('retired',retired=VERBS[parts[0]])
    if parts and parts[0] in VERBS and accepts(VERBS[parts[0]]):
        verb=VERBS[parts[0]]
        if len(parts)==1:return Command(verb)
        if len(parts)==2 and re.fullmatch(r'[0-9]+',parts[1]):
            if verb in PAGED_COMMANDS and 1<=int(parts[1])<=MAX_PAGE:
                return Command(verb,page=int(parts[1]))
            return Command('help')
    # Keep established compact Chinese aliases, including 鸣潮角色.
    if parts:
        for alias in ('鸣潮','异环','终末地'):
            if parts[0].startswith(alias) and parts[0][len(alias):] in VERBS:
                parts=[alias,parts[0][len(alias):],*parts[1:]]
                break
    if len(parts)<2:return Command('help')
    if parts[0] in GAMES and parts[1] in VERBS:
        game,verb=GAMES[parts[0]],VERBS[parts[1]]
    elif parts[1] in GAMES and parts[0] in VERBS:
        game,verb=GAMES[parts[1]],VERBS[parts[0]]
    else:return Command('help')
    if retired_reply(verb,game):return Command('retired',game,retired=verb)
    if not accepts(verb,game):return Command('help')
    rest=parts[2:]
    page=1
    if rest and re.fullmatch(r'[0-9]+',rest[-1]):
        if verb not in PAGED_COMMANDS or not 1<=int(rest[-1])<=MAX_PAGE:return Command('help')
        page=int(rest.pop())
    if not rest:return Command(verb,game,page=page)
    if verb in ('roles','guide') and len(rest)==1 and 1<=len(rest[0])<=64 and rest[0].isprintable():
        return Command(verb,game,role_name=rest[0],page=page)
    return Command('help')


LINK = re.compile(r'(?:https?://|www\.)[^\s<>]+', re.I)
# ASCII lookbehind: \w would also treat Chinese text as part of the name, so 官网example.com stayed a link.
DOMAIN = re.compile(r'(?<![A-Za-z0-9_@])(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s<>]*)?', re.I)


def mask_links(text):
    """Unapproved URLs and bare domains never reach QQ as links."""
    return DOMAIN.sub('[链接未启用]', LINK.sub('[链接未启用]', text))


def safe_text(text, *, urls_approved=False):
    # Always mask long numerical identifiers, including identifiers embedded in nicknames.
    text = re.sub(r'(?<!\d)\d{7,}(?!\d)', '***', str(text))
    if not urls_approved:
        text = mask_links(text)
    # Prevent platform mention tags / control characters copied from upstream data.
    text = re.sub(r'<@[^>]*>', '', text)
    return ''.join(c for c in text if c=='\n' or ord(c)>=32)[:1800]
