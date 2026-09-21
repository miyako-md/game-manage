from abc import ABC

from game_assistant.models import Capability, FetchResult


class BaseGameAdapter(ABC):
    game_id: str = ""
    display_name: str = ""
    section: str = "pc"  # "pc" | "mobile"
    capabilities: list[Capability] = []
    credentials_configured: bool = True

    def prepare_refresh(self) -> None:
        """Invalidate reusable reads before an explicit user refresh."""
        pass

    async def fetch(self, capability: Capability) -> FetchResult:
        if capability not in self.capabilities:
            return FetchResult(ok=False, error="不支持该能力")
        method = {
            Capability.ACCOUNT: self.fetch_account,
            Capability.STAMINA: self.fetch_stamina,
            Capability.PROGRESS: self.fetch_progress,
            Capability.ANNOUNCEMENT: self.fetch_announcement,
            Capability.EVENTS: self.fetch_events,
            Capability.NEWS: self.fetch_news,
            Capability.MATCH: self.fetch_match,
            Capability.STATS: self.fetch_stats,
            Capability.EXPLORATION: self.fetch_exploration,
            Capability.CALABASH: self.fetch_calabash,
            Capability.ROLES: self.fetch_roles,
            Capability.COMBAT: self.fetch_combat,
            Capability.ACTIVITIES: self.fetch_activities,
            Capability.RESOURCES: self.fetch_resources,
            Capability.GACHA: self.fetch_gacha,
            Capability.RECORD: self.fetch_record,
            Capability.REALESTATE: self.fetch_realestate,
            Capability.VEHICLES: self.fetch_vehicles,
            Capability.TEAMS: self.fetch_teams,
        }[capability]
        auth = getattr(self, '_auth', None)
        if auth:
            return await auth.fetch(self.game_id, capability, method)
        return await method()

    async def fetch_account(self) -> FetchResult:
        return FetchResult(ok=False, error="适配器未实现该能力")

    async def fetch_realestate(self) -> FetchResult:
        return FetchResult(ok=False, error="适配器未实现该能力")

    async def fetch_vehicles(self) -> FetchResult:
        return FetchResult(ok=False, error="适配器未实现该能力")

    async def fetch_teams(self) -> FetchResult:
        return FetchResult(ok=False, error="适配器未实现该能力")

    async def fetch_stamina(self) -> FetchResult:
        return FetchResult(ok=False, error="适配器未实现该能力")

    async def fetch_progress(self) -> FetchResult:
        return FetchResult(ok=False, error="适配器未实现该能力")

    async def fetch_announcement(self) -> FetchResult:
        return FetchResult(ok=False, error="适配器未实现该能力")

    async def fetch_events(self) -> FetchResult:
        return FetchResult(ok=False, error="适配器未实现该能力")

    async def fetch_news(self) -> FetchResult:
        return FetchResult(ok=False, error="适配器未实现该能力")

    async def fetch_match(self) -> FetchResult:
        return FetchResult(ok=False, error="适配器未实现该能力")

    async def fetch_stats(self) -> FetchResult:
        return FetchResult(ok=False, error="适配器未实现该能力")

    async def fetch_exploration(self) -> FetchResult:
        return FetchResult(ok=False, error="适配器未实现该能力")

    async def fetch_calabash(self) -> FetchResult:
        return FetchResult(ok=False, error="适配器未实现该能力")

    async def fetch_roles(self) -> FetchResult:
        return FetchResult(ok=False, error="适配器未实现该能力")

    async def fetch_gacha(self) -> FetchResult:
        return FetchResult(ok=False, error="适配器未实现该能力")

    async def fetch_combat(self) -> FetchResult:
        return FetchResult(ok=False, error="适配器未实现该能力")

    async def fetch_activities(self) -> FetchResult:
        return FetchResult(ok=False, error="适配器未实现该能力")

    async def fetch_resources(self) -> FetchResult:
        return FetchResult(ok=False, error="适配器未实现该能力")

    async def fetch_record(self) -> FetchResult:
        return FetchResult(ok=False, error="适配器未实现该能力")

    async def fetch_match_detail(self, match_id: str) -> FetchResult:
        return FetchResult(ok=False, error="该游戏不支持对局详情")
