"""Public professional esports data; unrelated to LCU accounts and matches."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

FAMILIES = {'lpl': 'LPL', 'first_stand': '全球先锋赛', 'msi': 'MSI',
            'worlds': '全球总决赛', 'ewc': '电竞世界杯', 'asian_games': '亚运会'}


class EsportsTournament(BaseModel):
    id: str
    source_id: str
    family: str
    season_year: int
    name: str
    source_url: str


class EsportsMatch(BaseModel):
    id: str
    source_id: str
    tournament_id: str
    team_a_id: str | None = None
    team_b_id: str | None = None
    team_a_name: str = '待定'
    team_b_name: str = '待定'
    start_at: datetime | None = None
    status: Literal['scheduled', 'live', 'completed', 'postponed', 'cancelled', 'unknown'] = 'unknown'
    score_a: int | None = None
    score_b: int | None = None
    best_of: int | None = None
    stage: str = ''
    round_name: str = ''
    winner_team_id: str | None = None
    source_url: str
    live_url: str | None = None
    vod_url: str | None = None


class EsportsTeam(BaseModel):
    id: str
    source_id: str
    name: str
    short_name: str = ''
    logo_url: str | None = None
    description: str = ''
    kind: Literal['club', 'national', 'unknown'] = 'unknown'
    tournament_ids: list[str] = Field(default_factory=list)
    source_url: str


class EsportsPlayer(BaseModel):
    id: str
    source_id: str
    nickname: str
    image_url: str | None = None
    source_url: str


class RosterMembership(BaseModel):
    team_id: str
    player_id: str
    scope: Literal['source_current', 'season_registered', 'match_played'] = 'source_current'
    position: str | None = None
    tournament_id: str | None = None
    match_id: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None


class ParseMeta(BaseModel):
    source_updated_at: datetime | None = None
    coverage: Literal['unknown', 'partial', 'complete', 'missing'] = 'unknown'
    issues: list[str] = Field(default_factory=list)


class GroupMeta(ParseMeta):
    group_key: str
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    attempt_state: Literal['never', 'ok', 'error', 'cooldown'] = 'never'


class CatalogParse(BaseModel):
    meta: ParseMeta
    tournaments: list[EsportsTournament] = Field(default_factory=list)
    missing_families: list[str] = Field(default_factory=list)


class MatchParse(BaseModel):
    meta: ParseMeta
    matches: list[EsportsMatch] = Field(default_factory=list)


class RosterParse(BaseModel):
    meta: ParseMeta
    team: EsportsTeam | None = None
    players: list[EsportsPlayer] = Field(default_factory=list)
    roster_memberships: list[RosterMembership] = Field(default_factory=list)


class EsportsSnapshot(BaseModel):
    schema_version: Literal[1] = 1
    season_year: int
    catalog: GroupMeta = Field(default_factory=lambda: GroupMeta(group_key='catalog'))
    tournaments: list[EsportsTournament] = Field(default_factory=list)
    matches: list[EsportsMatch] = Field(default_factory=list)
    teams: list[EsportsTeam] = Field(default_factory=list)
    players: list[EsportsPlayer] = Field(default_factory=list)
    roster_memberships: list[RosterMembership] = Field(default_factory=list)
    coverage: dict[str, GroupMeta] = Field(default_factory=dict)
    refresh_state: Literal['ok', 'partial', 'missing'] = 'missing'
