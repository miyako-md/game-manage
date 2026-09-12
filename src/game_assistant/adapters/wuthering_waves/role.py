from datetime import datetime, timedelta, timezone

from game_assistant.models import AccountInfo, StaminaInfo

REGEN_MINUTES_PER_POINT = 6


def parse_role_data(raw: dict, now: datetime) -> tuple[AccountInfo, StaminaInfo]:
    data = raw.get("data") or {}
    acc = AccountInfo(nickname=data.get("name"), level=data.get("level"))

    energy = data.get("energy") or {}
    current = int(energy.get("power") or 0)
    maximum = int(energy.get("max") or 0)
    expected_full_at = None
    ts = energy.get("refreshTimestamp")
    if ts:
        expected_full_at = datetime.fromtimestamp(int(ts) / 1000)
    elif maximum > current:
        expected_full_at = now + timedelta(
            minutes=REGEN_MINUTES_PER_POINT * (maximum - current))
    stamina = StaminaInfo(current=current, maximum=maximum,
                          expected_full_at=expected_full_at, updated_at=now)
    return acc, stamina
