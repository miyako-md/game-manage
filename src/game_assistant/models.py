from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


class Capability(str, Enum):
    ACCOUNT = "account"
    STAMINA = "stamina"
    PROGRESS = "progress"
    ANNOUNCEMENT = "announcement"
    NEWS = "news"
    MATCH = "match"
    STATS = "stats"
    EXPLORATION = "exploration"
    CALABASH = "calabash"
    ROLES = "roles"
    GACHA = "gacha"
    RECORD = "record"
    EVENTS = "events"


class StaminaInfo(BaseModel):
    current: int
    maximum: int
    expected_full_at: datetime | None = None
    updated_at: datetime


class AccountInfo(BaseModel):
    nickname: str | None = None
    level: int | None = None
    extra: dict = {}


class GameEvent(BaseModel):
    # 游戏内限时活动（版本公告正文解析，鸣潮/异环共用 event_calendar）
    name: str
    category: str | None = None  # 名称后缀方括号外的活动类型，如"限时联机战斗活动"
    start_at: datetime | None = None  # 相对开始（"版本更新后"）解析不出 → None
    end_at: datetime | None = None
    source_post_id: str | None = None
    source_title: str | None = None


class ProgressItem(BaseModel):
    # 周期进度（深塔/海墟/周本/千道门扉/终焉矩阵/周度游历/活跃度/结晶单质/电台等）
    name: str
    cur: int = 0
    total: int = 0
    refresh_at: datetime | None = None
    status: int = 0


class AnnouncementItem(BaseModel):
    title: str
    published_at: datetime | None = None
    url: str | None = None
    summary: str = ""


class DetectionSummary(BaseModel):
    # roleBox exploreIndex detectionInfoList 汇总：残象探寻已收录条目按级计数
    # （by_level 如 {"轻波级": n, "巨浪级": n, "怒涛级": n, "海啸级": n}）
    total: int = 0
    by_level: dict = {}


class AreaSummary(BaseModel):
    # 国家分组下的地区（areaInfoList 单条）：名称 + 探索度百分比；
    # itemList 明细不进模型（M4 再说）
    name: str
    progress: float | None = None


class CountryGroup(BaseModel):
    # roleBox exploreIndex exploreList 单组：country.countryName + countryProgress
    # （数字或百分比字符串，统一转 float）+ 组内地区列表
    name: str
    progress: float | None = None
    areas: list[AreaSummary] = []


class ExplorationData(BaseModel):
    # roleBox exploreIndex（2026-09-13 实测结构）：data.detectionInfoList（199 项）
    # + data.exploreList（4 组：瑝珑/黑海岸/黎那汐塔/罗伊冰原）+ data.open
    detections: DetectionSummary = DetectionSummary()
    country_groups: list[CountryGroup] = []


class RoleEntry(BaseModel):
    # roleBox roleData roleList 单项（角色练度墙）：等级/命链/突破/属性/武器等
    role_id: int | None = None
    name: str = ""
    level: int | None = None
    attribute: str | None = None
    breach: int | None = None
    chain: int | None = None
    star_level: int | None = None
    weapon: str | None = None
    icon_url: str | None = None
    is_main: bool = False


class CalabashData(BaseModel):
    # roleBox calabashData（数据坞）
    level: int | None = None
    base_catch: str | None = None  # 如 "20%"
    catch_quality: int | None = None
    cur_exp: int | None = None
    max_count: int | None = None


class MatchSummary(BaseModel):
    match_id: str
    queue_id: int | None = None
    mode: str = ""
    start_at: datetime | None = None
    duration_seconds: int | None = None
    win: bool | None = None
    champion_id: int | None = None
    kills: int | None = None
    deaths: int | None = None
    assists: int | None = None
    damage: int | None = None  # totalDamageDealtToChampions（生涯"最高伤害"纪录用）


class MatchParticipant(BaseModel):
    # 对局详情单人（GET /lol-match-history/v1/games/{gameId}，2026-09-13 国服实测）
    champion_id: int | None = None
    champion_name: str | None = None
    role_name: str | None = None  # 游戏内昵称
    level: int | None = None  # stats.champLevel
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    items: list[int] = []  # item0..item6 过滤 0
    damage: int | None = None  # totalDamageDealtToChampions
    gold: int | None = None  # goldEarned
    win: bool | None = None
    team_id: int | None = None
    is_own: bool = False


class MatchTeam(BaseModel):
    team_id: int | None = None
    win: bool | None = None
    participants: list[MatchParticipant] = []


class MatchDetail(BaseModel):
    match_id: str
    mode: str = ""
    start_at: datetime | None = None
    duration_seconds: int | None = None
    teams: list[MatchTeam] = []


class ChampionStat(BaseModel):
    # 常用英雄（生涯统计近 20 场口径）
    champion_id: int | None = None
    champion_name: str | None = None
    games: int = 0
    wins: int = 0


class StatsSummary(BaseModel):
    # 生涯统计+名场面（国服 match history 不支持翻页，口径 = 最近 20 场）
    total_games: int = 0
    wins: int = 0
    winrate: float | None = None  # 0-100
    avg_kills: float | None = None
    avg_deaths: float | None = None
    avg_assists: float | None = None
    top_champions: list[ChampionStat] = []  # 按场次降序前 5
    records: list[dict] = []  # [{"label": "单场最高击杀", "value": "22", "match_id": "..."}]


class FetchResult(BaseModel):
    ok: bool
    payload: Any = None
    error: str | None = None
