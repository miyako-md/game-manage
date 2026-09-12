import httpx
import respx


@respx.mock
async def test_send_skipped_when_key_empty():
    from game_assistant.notify.wechat_push import WeChatPushNotifier
    n = WeChatPushNotifier(provider="serverchan", send_key="")
    assert await n.send("t", "b") is False
    assert respx.calls.call_count == 0  # 未配置密钥时不得发起任何 HTTP 请求


@respx.mock
async def test_serverchan_send():
    from game_assistant.notify.wechat_push import WeChatPushNotifier
    route = respx.post("https://sctapi.ftqq.com/KEY.send").mock(
        return_value=httpx.Response(200, json={"code": 0}))
    n = WeChatPushNotifier(provider="serverchan", send_key="KEY")
    assert await n.send("标题", "内容") is True
    assert route.called


@respx.mock
async def test_pushplus_send():
    from game_assistant.notify.wechat_push import WeChatPushNotifier
    respx.post("https://www.pushplus.plus/send").mock(
        return_value=httpx.Response(200, json={"code": 200}))
    n = WeChatPushNotifier(provider="pushplus", send_key="K")
    assert await n.send("t", "b") is True


@respx.mock
async def test_http_error_returns_false():
    from game_assistant.notify.wechat_push import WeChatPushNotifier
    respx.post("https://sctapi.ftqq.com/KEY.send").mock(
        return_value=httpx.Response(500))
    n = WeChatPushNotifier(provider="serverchan", send_key="KEY")
    assert await n.send("t", "b") is False
