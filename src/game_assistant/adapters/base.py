from abc import ABC

from game_assistant.models import Capability, FetchResult


class BaseGameAdapter(ABC):
    game_id: str = ""
    display_name: str = ""
    section: str = "pc"  # "pc" | "mobile"
    capabilities: list[Capability] = []
    credentials_configured: bool = True

    async def fetch(self, capability: Capability) -> FetchResult:
        if capability not in self.capabilities:
            return FetchResult(ok=False, error="不支持该能力")
        method = {
            Capability.ACCOUNT: self.fetch_account,
            Capability.STAMINA: self.fetch_stamina,
            Capability.ACTIVITY: self.fetch_activity,
            Capability.PROGRESS: self.fetch_progress,
            Capability.ANNOUNCEMENT: self.fetch_announcement,
            Capability.NEWS: self.fetch_news,
            Capability.MATCH: self.fetch_match,
            Capability.EXPLORATION: self.fetch_exploration,
            Capability.CALABASH: self.fetch_calabash,
        }[capability]
        return await method()

    async def fetch_account(self) -> FetchResult:
        return FetchResult(ok=False, error="适配器未实现该能力")

    async def fetch_stamina(self) -> FetchResult:
        return FetchResult(ok=False, error="适配器未实现该能力")

    async def fetch_activity(self) -> FetchResult:
        return FetchResult(ok=False, error="适配器未实现该能力")

    async def fetch_progress(self) -> FetchResult:
        return FetchResult(ok=False, error="适配器未实现该能力")

    async def fetch_announcement(self) -> FetchResult:
        return FetchResult(ok=False, error="适配器未实现该能力")

    async def fetch_news(self) -> FetchResult:
        return FetchResult(ok=False, error="适配器未实现该能力")

    async def fetch_match(self) -> FetchResult:
        return FetchResult(ok=False, error="适配器未实现该能力")

    async def fetch_exploration(self) -> FetchResult:
        return FetchResult(ok=False, error="适配器未实现该能力")

    async def fetch_calabash(self) -> FetchResult:
        return FetchResult(ok=False, error="适配器未实现该能力")
