import logging

import httpx

logger = logging.getLogger(__name__)


class WeChatPushNotifier:
    def __init__(self, provider: str = "serverchan", send_key: str = ""):
        self.provider = provider
        self.send_key = send_key

    async def send(self, title: str, body: str) -> bool:
        if not self.send_key:
            logger.info("提醒渠道未启用（send_key 未配置），跳过推送: %s", title)
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                if self.provider == "serverchan":
                    resp = await client.post(
                        f"https://sctapi.ftqq.com/{self.send_key}.send",
                        data={"title": title, "desp": body},
                    )
                    code = resp.json().get("code")
                    ok = code == 0
                elif self.provider == "pushplus":
                    resp = await client.post(
                        "https://www.pushplus.plus/send",
                        json={"token": self.send_key, "title": title,
                              "content": body, "template": "txt"},
                    )
                    code = resp.json().get("code")
                    ok = code == 200
                else:
                    logger.warning("未知推送 provider: %s", self.provider)
                    return False
            if not ok:
                # A provider can echo submitted tokens/URLs in any response
                # field, including code. Only bounded numeric codes are safe.
                safe_code = code if type(code) is int and -1_000_000 <= code <= 1_000_000 else "unknown"
                logger.warning("微信推送响应异常: HTTP %s, provider_code=%s",
                               resp.status_code, safe_code)
            return ok
        except Exception as exc:
            # Exception messages/tracebacks may contain the credential URL.
            logger.warning("微信推送失败 (%s)", type(exc).__name__)
            return False


def build_notifier(settings) -> WeChatPushNotifier:
    return WeChatPushNotifier(provider=settings.notify_provider,
                              send_key=settings.notify_send_key)
