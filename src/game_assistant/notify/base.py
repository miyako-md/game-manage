from typing import Protocol

from game_assistant.config import Settings
from game_assistant.notify.wechat_push import WeChatPushNotifier


class Notifier(Protocol):
    name: str

    async def send(self, title: str, body: str) -> bool: ...


def build_notifier(settings: Settings) -> Notifier:
    return WeChatPushNotifier(provider=settings.notify_provider,
                              send_key=settings.notify_send_key)
