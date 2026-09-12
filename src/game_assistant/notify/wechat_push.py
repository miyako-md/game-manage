import logging

import httpx

logger = logging.getLogger(__name__)


class WeChatPushNotifier:
    name = "wechat_push"

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
                    ok = resp.json().get("code") == 0
                elif self.provider == "pushplus":
                    resp = await client.post(
                        "https://www.pushplus.plus/send",
                        json={"token": self.send_key, "title": title,
                              "content": body, "template": "txt"},
                    )
                    ok = resp.json().get("code") == 200
                else:
                    logger.warning("未知推送 provider: %s", self.provider)
                    return False
            if not ok:
                logger.warning("微信推送响应异常: %s", resp.text[:200])
            return ok
        except Exception:
            logger.warning("微信推送失败", exc_info=True)
            return False
