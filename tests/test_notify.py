import httpx
import respx
import logging
import sys

import pytest


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


@pytest.mark.parametrize("case, expected", [
    ("success", True), ("network_error", False), ("provider_error", False),
])
@respx.mock
def test_runtime_notifier_logs_never_expose_push_key(tmp_path, monkeypatch, case, expected):
    """Exercise the actual runner logging setup and real HTTP notifier together."""
    from game_assistant import runtime
    from game_assistant.notify.wechat_push import WeChatPushNotifier

    fake_key = "fake-review-sendkey-private"
    url = f"https://sctapi.ftqq.com/{fake_key}.send"
    route = respx.post(url)
    if case == "success":
        route.respond(200, json={"code": 0})
    elif case == "network_error":
        route.mock(side_effect=httpx.ConnectError(f"Failed request to {url}"))
    else:
        # Both message and code can be untrusted strings supplied by a provider.
        route.respond(403, json={"code": fake_key, "message": f"Rejected {url}"})

    runtime_dir = tmp_path / "data" / "runtime" / "sandbox-18099"
    monkeypatch.setattr(runtime, "__file__", str(tmp_path / "src" / "game_assistant" / "runtime.py"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["runtime.py", "--port", "18099", "--runtime-id", "a" * 32,
                                      "--runtime-dir", str(runtime_dir), "--sandbox"])
    # main() configures the real root handlers and streams. Isolate and restore
    # pytest's own capture handlers so basicConfig(force=True) cannot close them.
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [])
    monkeypatch.setattr(root, "level", root.level)
    for name in ("httpx", "httpcore"):
        logger = logging.getLogger(name)
        monkeypatch.setattr(logger, "level", logger.level)
    monkeypatch.setattr(sys, "stdout", sys.stdout)
    monkeypatch.setattr(sys, "stderr", sys.stderr)
    sent = []

    async def exercise_notifier(app, port, directory, runtime_id):
        sent.append(await WeChatPushNotifier(send_key=fake_key).send("test", "test"))

    monkeypatch.setattr(runtime, "_serve", exercise_notifier)
    try:
        runtime.main()
        for handler in root.handlers:
            handler.flush()
        log_text = (runtime_dir / "service.log").read_text(encoding="utf-8")
        assert sent == [expected]
        assert route.called
        assert fake_key not in log_text
        assert url not in log_text
        assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
        assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING
        if case == "network_error":
            assert "ConnectError" in log_text
            assert "Traceback" not in log_text
        elif case == "provider_error":
            assert "403" in log_text
    finally:
        for handler in root.handlers[:]:
            root.removeHandler(handler)
            handler.close()
        monkeypatch.undo()
        # Restore effective-level caches after monkeypatch restores logger.level.
        root.setLevel(root.level)
