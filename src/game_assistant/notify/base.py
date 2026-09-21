from game_assistant.config import Settings
from game_assistant.notify.wechat_push import WeChatPushNotifier


def build_notifier(settings: Settings) -> WeChatPushNotifier:
    return WeChatPushNotifier(provider=settings.notify_provider,
                              send_key=settings.notify_send_key)
