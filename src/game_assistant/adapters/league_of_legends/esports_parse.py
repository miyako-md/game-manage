"""Pure parsing of observed Tencent website data (not a supported public API)."""
import json
import re
from datetime import datetime
from urllib.parse import urlsplit

from game_assistant.event_calendar import BEIJING_TZ
from .esports_models import (
    FAMILIES, CatalogParse, MatchParse, RosterParse, ParseMeta, EsportsTournament,
    EsportsMatch, EsportsTeam, EsportsPlayer, RosterMembership,
)

# Official catalogue family IDs; no verified Asian Games family yet.
FAMILY_IDS = {'5': 'lpl', '220': 'first_stand', '8': 'msi', '1': 'worlds', '227': 'ewc'}
POSITIONS = {'1': '上路', '2': '中路', '3': '下路', '4': '辅助', '5': '打野'}
BASE = 'https://lpl.qq.com/web202301/'


def source_id(value):
    text = str(value) if isinstance(value, (str, int)) and not isinstance(value, bool) else ''
    return text if re.fullmatch(r'[0-9]{1,30}', text) and int(text) > 0 else None


def text(value, limit=200):
    return value.strip()[:limit] if isinstance(value, str) else ''


def source_time(value):
    try:
        dt = datetime.fromisoformat(value) if isinstance(value, str) else None
        return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=BEIJING_TZ)
    except (ValueError, OverflowError):
        return None


def image_url(value):
    value = text(value, 2048)
    if value.startswith('//'):
        value = 'https:' + value
    try:
        u = urlsplit(value)
        if (u.scheme == 'https' and not u.username and not u.password and u.port in (None, 443)
                and u.hostname in {'img.crawler.qq.com', 'shp.qpic.cn', 'game.gtimg.cn',
                                   'ossweb-img.qq.com', 'puui.qpic.cn'}):
            return value
    except ValueError:
        pass
    return None


def decode_public_payload(value: str) -> dict:
    value = value.strip().lstrip('\ufeff')
    if not value.startswith('{'):
        match = re.fullmatch(r'(?:var\s+)?[A-Za-z_$][\w$]*\s*=\s*(\{.*\})\s*;?', value, re.S)
        if not match:
            raise ValueError('unsupported public data wrapper')
        value = match.group(1)
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError('expected object')
    return parsed


def _meta(raw):
    return ParseMeta(source_updated_at=source_time(raw.get('lastUpdateTime') or raw.get('lastUpTime')))


def _unique(rows, meta):
    seen, conflicts = {}, set()
    for row in rows:
        if row.id in seen and row != seen[row.id]:
            conflicts.add(row.id)
        seen[row.id] = row
    if conflicts:
        meta.issues.append('重复编号内容冲突')
        meta.coverage = 'partial'
    return [r for key, r in seen.items() if key not in conflicts]


def parse_catalog(raw: dict, season_year: int) -> CatalogParse:
    msg = raw.get('msg')
    if not isinstance(msg, dict) or not isinstance(msg.get('sGameList'), dict):
        raise ValueError('invalid catalogue')
    result = CatalogParse(meta=_meta(raw))
    for family_id, family in FAMILY_IDS.items():
        rows = msg['sGameList'].get(family_id, [])
        if not isinstance(rows, list):
            result.meta.issues.append('赛事列表结构异常')
            continue
        for row in rows:
            if not isinstance(row, dict):
                result.meta.issues.append('赛事条目结构异常')
                continue
            if str(row.get('GameYear')) != str(season_year):
                continue
            sid = source_id(row.get('GameId'))
            if not sid or str(row.get('bGameId')) != family_id or not text(row.get('GameName')):
                result.meta.issues.append('赛事编号或名称异常')
                continue
            result.tournaments.append(EsportsTournament(
                id=f'tencent:tournament:{sid}', source_id=sid, family=family, season_year=season_year,
                name=text(row['GameName']), source_url=f'{BASE}event.html?tabId=schedule&gameId={sid}'))
    result.tournaments = _unique(result.tournaments, result.meta)
    found = {t.family for t in result.tournaments}
    result.missing_families = [f for f in FAMILIES if f not in found]
    if result.missing_families or result.meta.issues:
        result.meta.coverage = 'partial'
    return result


def _score(value):
    return int(value) if re.fullmatch(r'[0-9]{1,2}', str(value)) else None


def parse_matches(raw: dict, tournament: EsportsTournament) -> MatchParse:
    if not isinstance(raw.get('msg'), list) or len(raw['msg']) > 10000:
        raise ValueError('invalid match list')
    result = MatchParse(meta=_meta(raw))
    for row in raw['msg']:
        if not isinstance(row, dict) or str(row.get('GameId')) != tournament.source_id:
            result.meta.issues.append('忽略不属于本赛季或异常的比赛')
            continue
        sid = source_id(row.get('bMatchId'))
        if not sid:
            result.meta.issues.append('比赛编号缺失')
            continue
        a, b = source_id(row.get('TeamA')), source_id(row.get('TeamB'))
        aid, bid = (f'tencent:team:{a}' if a else None), (f'tencent:team:{b}' if b else None)
        names = re.split(r'\s+vs\s+', text(row.get('bMatchName')), flags=re.I)
        status = {'1': 'scheduled', '2': 'live', '3': 'completed'}.get(str(row.get('MatchStatus')), 'unknown')
        sa, sb = _score(row.get('ScoreA')), _score(row.get('ScoreB'))
        winner = aid if str(row.get('MatchWin')) == '1' else bid if str(row.get('MatchWin')) == '2' else None
        if status not in ('completed', 'live'):
            sa = sb = winner = None
        elif status == 'live':
            winner = None
        elif (sa is None or sb is None or sa == sb or not winner
              or (winner == aid and sa < sb) or (winner == bid and sb < sa)):
            status, winner = 'unknown', None
            result.meta.issues.append('比赛结果待核实')
        start = source_time(row.get('MatchDate'))
        if start is None:
            result.meta.issues.append('比赛时间暂缺')
        bo = re.fullmatch(r'BO([13579])', text(row.get('GameModeName')).upper())
        url = f'{BASE}live.html?bgid={tournament.source_id}&bmid={sid}'
        news = source_id(row.get('NewsId'))
        result.matches.append(EsportsMatch(
            id=f'tencent:match:{sid}', source_id=sid, tournament_id=tournament.id,
            team_a_id=aid, team_b_id=bid,
            team_a_name=text(row.get('TeamShortNameA')) or (names[0] if len(names) == 2 else '待定'),
            team_b_name=text(row.get('TeamShortNameB')) or (names[1] if len(names) == 2 else '待定'),
            start_at=start, status=status, score_a=sa, score_b=sb, winner_team_id=winner,
            best_of=int(bo[1]) if bo else None, stage=text(row.get('GameTypeName')),
            round_name=text(row.get('GameProcName')), source_url=url,
            live_url=url if status in ('live', 'scheduled') else None,
            vod_url=f'{BASE}video_detail.shtml?nid={news}&bMatchId={sid}' if news and status == 'completed' else None))
    result.matches = _unique(result.matches, result.meta)
    if result.meta.issues:
        result.meta.coverage = 'partial'
        result.meta.issues = list(dict.fromkeys(result.meta.issues))
    return result


def parse_team(raw: dict, tournament_ids: list[str]) -> RosterParse:
    msg = raw.get('msg')
    if not isinstance(msg, dict) or not isinstance(msg.get('baseInfo'), dict):
        raise ValueError('invalid team')
    base = msg['baseInfo']
    sid = source_id(base.get('TeamId'))
    if not sid or not text(base.get('TeamName')) or not isinstance(msg.get('activePlayers'), list):
        raise ValueError('invalid roster')
    team = EsportsTeam(id=f'tencent:team:{sid}', source_id=sid, name=text(base['TeamName']),
                      short_name=text(base.get('TeamShortName')), logo_url=image_url(base.get('TeamLogo')),
                      description=text(base.get('TeamDesc'), 4000), tournament_ids=tournament_ids,
                      source_url=f'{BASE}team-detail.html?tid={sid}')
    result = RosterParse(meta=_meta(raw), team=team)
    if len(msg['activePlayers']) > 200:
        result.meta.issues.append('成员列表超出安全上限，仅保留部分资料')
    for row in msg['activePlayers'][:200]:
        pid = source_id(row.get('MemberId')) if isinstance(row, dict) else None
        if not pid or not text(row.get('NickName')):
            result.meta.issues.append('部分成员资料缺失')
            continue
        player = EsportsPlayer(id=f'tencent:player:{pid}', source_id=pid,
                              nickname=text(row['NickName']), image_url=image_url(row.get('UserIcon')),
                              source_url=f'{BASE}player-detail.html?mbid={pid}')
        result.players.append(player)
        positions = [POSITIONS.get(p) for p in str(row.get('GamePlace', '')).split(',') if p]
        result.roster_memberships.append(RosterMembership(
            team_id=team.id, player_id=player.id,
            position=' / '.join(positions) if positions and all(positions) else None))
    result.players = _unique(result.players, result.meta)
    valid = {p.id for p in result.players}
    memberships = {m.player_id: m for m in result.roster_memberships if m.player_id in valid}
    result.roster_memberships = list(memberships.values())
    if result.meta.issues:
        result.meta.coverage = 'partial'
    return result
