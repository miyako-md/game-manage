"""Shared LCU match rules for recent snapshots and the personal archive."""

# Preserve the existing snapshot rule for remakes/aborted short matches.
REMAKE_SECONDS = 300


def is_remake(stats: dict, duration_seconds) -> bool:
    if stats.get("gameEndedInEarlySurrender") is True:
        return True
    return (isinstance(duration_seconds, (int, float)) and not isinstance(duration_seconds, bool)
            and 0 <= duration_seconds < REMAKE_SECONDS)
