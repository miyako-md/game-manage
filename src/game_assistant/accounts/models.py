"""Shared identities and results for website and QQ query services.

Account and role identifiers are internal keys, never upstream game UIDs.
QueryResult keeps missing data and unknown history completeness as None.
Times at service boundaries are ISO 8601 strings. RefreshReceipt.state is
queued or coalesced; upstream failures belong to QueryResult.state instead.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AccountScope:
    user_id: str
    account_id: str
    role_id: str


@dataclass(frozen=True, slots=True)
class QueryResult:
    payload: dict | list | None
    fetched_at: str | None
    state: str
    complete: bool | None


@dataclass(frozen=True, slots=True)
class RefreshReceipt:
    job_id: str
    state: str
