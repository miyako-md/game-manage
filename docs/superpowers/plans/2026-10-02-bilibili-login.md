# Bilibili Three-Mode Login Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为当前 B 站资讯账号提供默认扫码、账号密码、手机号验证码登录和 Cookie 备用导入，验证成功后才替换加密凭据。

**Architecture:** 独立 HTTPX provider 负责协议和候选验证，登录 service 负责内存会话、限流和提交，Vue 组件负责人工验证及展示。复用现有 DPAPI 存储与资讯采集；新路由使用多一层 login 的前缀，隔离通用游戏登录。六个任务按依赖顺序执行，正式服务的变更留到独立部署阶段。

**Tech Stack:** Python >=3.11、FastAPI、HTTPX、PyCryptodome、qrcode、Vue 3、Node test、pytest/respx；Windows DPAPI；保留 bilibili-api-python >=17.4.1,<18（当前锁定 17.4.2）。

**Spec:** [2026-10-02-bilibili-login-design.md](../specs/2026-10-02-bilibili-login-design.md)，已获用户书面确认；执行者先读设计与本计划。

## Global Constraints

- 只扩展共用的 B 站资讯采集账号；不增加游戏 B 服登录、多账号、账号注销、安全中心接口、自动续期、代理切换或浏览器自动化。
- 默认扫码，保留密码、短信和 Cookie 备用方式；人工完成验证码；真实账号验收由用户自行操作。
- 新 API 前缀 /api/auth/bilibili-source/login；写请求头 X-Game-Assistant: 1，受信任 Host/Origin，JSON 请求体上限 16 KiB，响应 no-store/no-cache/no-referrer。
- sid 由随机 32 字节生成；最多一个活动会话、脱敏终态最多保留 60 秒、记录上限 16；新会话使旧会话失效但保留已保存账号。
- 会话最多 10 分钟；QR 本地展示最多 180 秒；人工挑战本地最多 120 秒且一次使用后消耗；pending_save 最多 120 秒且不超过会话期限。
- 每会话最多一个上游操作在途；密码或短信码提交最多 5 次；新会话每分钟最多 10 次。
- 大陆手机号固定 +86；同手机号短信冷却 60 秒，全局每 10 分钟最多 5 次，网络访问前预留额度，失败/超时不自动重发。
- QR 前后端每 3 秒最多一次；上游请求超时 10 秒，交换加验证总时限 60 秒，前端等待上限 75 秒。
- 密码/短信码不落盘、不进入会话或日志；候选验证后才 DPAPI 原子保存；失败、取消、超时或旧结果不覆盖原账号。
- QR 成功立即捕获凭据，不再次消费票据；旧 URL 与新 Set-Cookie 格式均需验证，空值、冲突或未知格式拒绝。
- 上游 HTTP 412 映射 502 / UPSTREAM_RESTRICTED，停止轮询；不绕过。额外安全验证提示用户去固定官方登录页处理，不调用安全中心接口。
- 正式 config.toml、data、凭据、frontend/dist、自启动设置和 8010 服务在实现/测试阶段不变；测试只用假账号和隔离临时目录。
- Git 作者缺失不阻塞执行；不虚构身份或更改配置。以下各任务的提交检查点仅在已有身份时提交列明文件，否则保留差异和验证记录，不推送。

## Review Focus

五项易漏条件及所属测试：

1. QR 同一 Cookie 重复同值与重复冲突值：前者可解析，后者拒绝且原账号不变（Task 1 的 test_qr_duplicate_cookie_values）。
2. 密码含空格/Unicode、加密字节超限：原样加密，超限给固定错误且不提交（Task 2 的 test_password_exact_bytes_and_rsa_limit）。
3. 发短信超时后换会话：同手机号 60 秒内仍不可重发（Task 3 的 test_sms_timeout_cooldown_survives_new_session）。
4. 两个面板交错创建、取消、返回：旧取消和迟到结果不能影响新账号（Task 3 的 test_stale_panel_cancel_and_result）。
5. DPAPI 已保存而 next_retry 写 SQLite 失败：仍报告账号保存成功，提供采集可重试提示（Task 3 的 test_retry_reset_failure_after_saved_account）。

---

## 文件与接口约定

新增：

- src/game_assistant/auth/bilibili_provider.py：BilibiliLoginProvider、协议错误、QR 与验证结果类型。
- src/game_assistant/auth/bilibili_service.py：BilibiliLoginService、BilibiliLoginError、会话状态和限流。
- src/game_assistant/auth/bilibili_routes.py：新 router、Pydantic 请求模型及仅覆盖 B 站认证路径的有界请求体中间件。
- frontend/src/bilibili-auth-api.js、frontend/src/components/BilibiliLoginPanel.vue，以及同名 .test.js。
- tests/test_bilibili_auth_provider.py、tests/test_bilibili_auth_service.py、tests/test_bilibili_auth_routes.py。

修改：sources/bilibili_service.py、sources/bilibili_routes.py、api.py、必要时 auth/routes.py 的固定校验文案、BilibiliSourcePanel.vue/.test.js、pyproject.toml、uv.lock、docs/community-login.md、docs/bilibili-source.md。不修改 CredentialStore 的加密格式。

公共类型在 provider 文件定义：

    QrChallenge(polling_key: str, image_data_url: str, display_for: int)
    QrResult(state: str, credentials: dict[str, str] | None)
    VerifiedBilibiliAccount(credentials: dict[str, str], uid: str,
                           nickname: str, validated_at: float)

QrResult.state 只允许 waiting_scan / waiting_confirm / expired / credential_ready；credential_ready 仅为内部结果，不能向前端返回原始 credentials。VerifiedBilibiliAccount 只能由成功验证产生。

Provider 每个会话独立实例及 HTTPX 客户端；默认 trust_env=False、TLS 校验开启、follow_redirects=False、timeout=10。允许注入 client_factory 和 wall_clock 用于测试。协议错误用 BilibiliProtocolError(error_code: str, status: int, retry_after: int | None = None)，禁止接受上游 message 为用户文案。

Service 对外失败用 BilibiliLoginError(detail: str, status: int, error_code: str, state: str | None = None, retry_after: int | None = None)。公开会话状态只允许 ready / waiting_scan / waiting_confirm / sms_sent / verifying / pending_save / complete / blocked / expired / cancelled / failed。

## Task 1: 隔离环境与可验证的扫码 provider

**Files:** Create provider、tests/test_bilibili_auth_provider.py；Modify pyproject.toml、uv.lock（仅显式声明已使用的 qrcode 依赖时）。

**Interfaces:**
- Produces: normalize_cookie_input(values: dict[str,str]) -> dict[str,str]。
- Produces: BilibiliLoginProvider.start_qr() -> QrChallenge、poll_qr(polling_key: str) -> QrResult、validate_credentials(values: dict[str,str]) -> VerifiedBilibiliAccount，均 async；aclose() -> None 也是 async。
- Produces: async _resolve_credentials(data: dict, response: httpx.Response) -> dict[str,str]，供 Task 2 复用；内部统一一次解码。

- [ ] **Step 1: 建立独立执行目录。** 用 using-git-worktrees 在 C:/Users/73602/Documents/Codex/2026-10-02/task/game-manage-bilibili-login 建立 feat/bilibili-login；路径已存在则核对后使用新唯一目录，不覆盖。从原目录仅复制本次已批准 spec/plan；不复制 config.toml、data、凭据或旧 dist。核对分支、未提交修改和 workspace instructions。在新目录按锁文件准备独立 .venv/frontend 依赖（uv sync --locked --extra dev，frontend 中 npm ci）；不复用指向正式源码的 editable 安装。
- [ ] **Step 2: 写失败测试。** provider fixture 只使用 respx 和固定假值 FAKE_SESS/FAKE_JCT、UID 10001，nav 返回 isLogin=true。先写下列生成测试，再加入 QR 状态、旧查询与新 Set-Cookie、重复 Cookie、未知/空结果、恶意 URL、跳转上限和 UID 不符测试；禁止真实网络。

    # test_qr_generation_stays_in_memory(provider, tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)
    respx.get(QR_GENERATE).respond(200, json={"code": 0, "data": {
        "url": "https://passport.bilibili.com/login?test_only=FAKE",
        "qrcode_key": "FAKE_QR_KEY"}})
    qr = await provider.start_qr()
    assert qr.polling_key == "FAKE_QR_KEY"
    assert qr.image_data_url.startswith("data:image/png;base64,")
    assert list(tmp_path.iterdir()) == []

- [ ] **Step 3: 运行确认失败。** 在新目录运行 .venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider tests/test_bilibili_auth_provider.py，应因新增模块/接口缺失或行为断言失败；环境故障不算红灯。
- [ ] **Step 4: 实现最小 provider。** QR_GENERATE 为 https://passport.bilibili.com/x/passport-login/web/qrcode/generate?source=main-fe-header，QR_POLL 为同域 /x/passport-login/web/qrcode/poll。仅识别业务码 86101/86090/86038/0，完成响应一次捕获。跨域交换按 spec 的两个精确域名、/x/passport-login/web/crossDomain、HTTPS 默认端口、最多 3 次跳转处理；只允许最终 www.bilibili.com 根页面终止。调用固定 https://api.bilibili.com/x/web-interface/nav 验证 code=0、isLogin=true、正整数 UID 与 DedeUserID 一致。旧查询解析一次解码，Set-Cookie/导入用规范化器一次解码，内部提交不再 unquote。以已安装 17.4.2 的 data/api/login.json 为只读协议参考，不调用其旧扫码解析、不复制未审 PR 补丁。
- [ ] **Step 5: 运行确认通过。** 同一测试命令须全部通过；test_qr_duplicate_cookie_values 断言同值重复得到 FAKE_SESS、冲突值抛协议错误；未知域名/路径不得产生出站请求。nav 匿名/畸形/412/429/网络异常不能产生 VerifiedBilibiliAccount。补充断言二维码和凭据不进入文件/异常文本。
- [ ] **Step 6: 保存检查点。** git diff --check，核对只有本任务文件；已有作者身份时提交 feat: add verified Bilibili QR login provider，否则保留差异继续下一任务。

## Task 2: 人工挑战、密码与短信协议

**Files:** Modify provider、tests/test_bilibili_auth_provider.py。

**Interfaces:**
- Consumes: Task 1 的规范化、_resolve_credentials、验证和协议错误类型。
- Produces async: get_captcha() -> dict[str,str]，返回 gt/challenge/token，仅供 service 使用。
- Produces async: login_password(username: str, password: str, captcha: dict[str,str]) -> dict[str,str]。
- Produces async: send_sms(mobile: str, captcha: dict[str,str]) -> str（captcha_key）；login_sms(mobile: str, code: str, captcha_key: str) -> dict[str,str]。

- [ ] **Step 1: 写失败测试。** test_password_exact_bytes_and_rsa_limit 使用测试生成的 RSA 密钥和盐 fake-salt-，抓取表单并用私钥解密；断言解密结果等于 ("fake-salt-" + " 密码123 ").encode("utf-8")，超限时上游 POST 次数为 0。另写 test_captcha_proof_required、test_sms_ticket_and_country_binding、test_extra_verification_is_not_success、test_no_raw_upstream_message；断言手机号/cid=86、短信票据与验证码准确，缺证明或状态 1/2/5 不产生候选成功，未知状态拒绝。
- [ ] **Step 2: 确认红灯。** 运行 .venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider tests/test_bilibili_auth_provider.py；新增方法缺失/断言应失败。
- [ ] **Step 3: 实现方法。** GET /x/passport-login/captcha 取得当前挑战，GET /x/passport-login/web/key 后立即用 Crypto.Cipher.PKCS1_v1_5 加密 salt+原密码。密码 POST /x/passport-login/web/login；短信 POST /x/passport-login/web/sms/send 和 /web/login/sms，全部位于 passport.bilibili.com。表单字段对照已安装 login_v2.py 与 login.json，密码保留原字符；server-owned token/challenge 与人类 validate/seccode 组合。已知成功状态才解析，额外验证映射 SECURITY_VERIFICATION_REQUIRED，未知格式映射 UNSUPPORTED_RESPONSE；不调用 safecenter。一次请求不自动重试，密码/码只在调用局部存在。
- [ ] **Step 4: 确认绿灯与 QR 回归。** 同一 provider 测试文件全部通过；用 caplog 和假敏感值断言错误日志/异常没有手机号、密码、验证码或原始 message。
- [ ] **Step 5: 保存检查点。** 仅本任务文件；已有身份时提交 feat: add human-verified Bilibili password and SMS login，否则记录差异。

## Task 3: 会话、限流、取消与原子保存

**Files:** Create service、tests/test_bilibili_auth_service.py；Modify sources/bilibili_service.py；Test tests/test_bilibili_integration.py、tests/test_auth_store.py。

**Interfaces:**
- Consumes: Task 1/2 provider_factory，每个 sid 创建独立 provider。
- Produces: BilibiliLoginService(source, provider_factory, clock=time.monotonic, wall_clock=time.time)；source=None 时 SOURCE_UNCONFIGURED。
- Produces sync: status() -> dict、session_status(sid: str) -> dict。status 返回 configured/state/uid/nickname/validated_at/message；账号 state 为 unconfigured/configured/validated/expired/storage_error，只有本次运行验证过才为 validated。session_status 返回 session_id/mode/state/expires_in/can_commit，以及可选 detail/error_code/retry_after/account。
- Produces async: start(mode: str)、cancel(sid)、captcha(sid)、password(sid, username, password, proof)、sms_send(sid, mobile, proof)、sms_submit(sid, code)、qr_poll(sid)、cookie(sid, values)、commit(sid)、import_legacy(values)，均返回 dict；aclose() -> None。start 的字段固定为 session_id/mode/state/expires_in，QR 另返回 qr_image（data URL）和 qr_expires_in；成功为 ok/state=complete/account。所有会访问上游或提交账号的方法额外接受关键字 is_disconnected: Callable[[], Awaitable[bool]] | None = None，只在当前调用局部使用，不写会话；路由传入 request.is_disconnected。提交前先 await 检查断连，再进入无 await 的版本复查/原子保存段。
- Produces: BilibiliService.commit_verified_account(account: VerifiedBilibiliAccount) -> dict；同步检查采集状态与原子保存，返回可选 warning，不跨网络 await。该文件新增 BilibiliSaveBusy(SourceError)，供运行中的采集抛出，service 固定映射为 409/pending_save；CredentialStoreError 映射安全存储错误，不读取原始异常为文案。BilibiliLoginService 是唯一 HTTP 提交调用方。

- [ ] **Step 1: 写失败测试。** service fixture case 包含 service、可 advance 的假单调时钟、带 busy/saved 的假 source、共享 calls 计数的假 provider。假 provider 只返回 Task 1 定义的类型，不访问网络。先锁定 pending_save 的断言，再加入全部时间/限额测试。

    # test_pending_save_does_not_reconsume_qr(case)
    case.source.busy = True
    sid = (await case.service.start("qr"))["session_id"]
    with pytest.raises(BilibiliLoginError) as caught:
        await case.service.qr_poll(sid)
    assert (caught.value.status, caught.value.state) == (409, "pending_save")
    assert case.source.saved == []
    case.source.busy = False
    assert (await case.service.commit(sid))["state"] == "complete"
    assert case.calls["qr_poll"] == 1
    assert len(case.source.saved) == 1

- [ ] **Step 2: 确认红灯。** 运行 .venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider tests/test_bilibili_auth_service.py；新增 service/提交方法缺失或断言失败。
- [ ] **Step 3: 实现会话。** 将 Global Constraints 的全部数值设为命名常量；一次只允许一个在途动作，网络在锁外，结果按 sid/generation/期限/revision/取消状态复查。短信额度先预留并按手机号摘要跨会话保留；验证挑战一次消耗、固定 mode 与首次账号/手机号。QR 早于 3 秒的请求读缓存；交换总超时 60 秒。候选只保留内存，pending_save 重试前重新验证；新会话、过期、关闭清理 provider 与候选，终态只保留脱敏字段。
- [ ] **Step 4: 实现保存出口。** 保留 .bilibili.credentials.json 和 DPAPI 格式。先确认原文件可解密、没有采集运行、revision 仍匹配；同步关键段仅替换 bilibili 和独立 bilibili_meta（uid/nickname/validated_at），保留其他根记录，六项 credential 白名单不混入 metadata。保存成功才提升 revision；失败保留旧文件/账号。next_retry 重置失败返回 complete 与“账号已保存，采集刷新可重试”，不回滚已经成功保存的账号；不清公共历史或其他平台快照。
- [ ] **Step 5: 验证所有边界。** test_sms_timeout_cooldown_survives_new_session：发送超时、换 sid 后 +59 秒仍 429，+60 秒可重新人工验证后发送，calls["sms_send"] 仅增加一次。test_stale_panel_cancel_and_result 用 asyncio.Event 阻塞旧请求，创建新会话再释放旧结果，断言旧结果不保存、旧 DELETE 不取消新会话。另断言 600/180/120/60 秒边界、5 次提交、10 次创建、5 次全局短信、记录<=16、同会话并发 409、关闭/断连与存储损坏拒绝写入。test_retry_reset_failure_after_saved_account 注入 SQLite 错误，断言 complete、新账号可重新加载、历史不变、提示可重试。
- [ ] **Step 6: 运行绿灯与存储回归。** 运行 .venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider tests/test_bilibili_auth_service.py tests/test_bilibili_integration.py tests/test_auth_store.py，全部通过。假敏感值不能出现在序列化状态、日志或未加密文件中；不声称清理引用能物理擦除 Python 内存。
- [ ] **Step 7: 保存检查点。** 已有身份时提交 feat: manage Bilibili login sessions and atomic account replacement，仅列明本任务文件。

## Task 4: 路由、安全边界与旧入口兼容

**Files:** Create auth/bilibili_routes.py、tests/test_bilibili_auth_routes.py；Modify api.py、sources/bilibili_routes.py，必要时 auth/routes.py 的固定校验文案；Test tests/test_api_security.py、tests/test_auth_routes.py。

**Interfaces:**
- Consumes: Task 3 service 公共方法与 BilibiliLoginError。
- Produces: install_bilibili_auth_routes(app, login_service) -> None；BilibiliBodyLimitMiddleware(app, max_bytes=16384) 的 async __call__(scope, receive, send)。
- Produces: create_app 增加可选 bilibili_login_service=None 测试注入参数；app.state.bilibili_auth 保存实例。
- Changes: install_bilibili_routes(app, source_service, login_service=None)，旧导入转交 import_legacy，资讯状态 login 使用脱敏 status。

- [ ] **Step 1: 写失败测试。** TestClient 使用临时 Settings/db、start_scheduler=False、模拟 service，并提供 X-Game-Assistant: 1；参数化 spec 的全部 11 条新路径，断言派发到对应方法而不是通用游戏 service。test_legacy_import_cannot_skip_validation 断言匿名候选拒绝、原凭据不变。test_safe_errors_and_body_limit 断言 422 不含假密码/码，500/409 保留安全 pending_save 字段，所有响应含 no-store。
- [ ] **Step 2: 确认红灯。** 运行 .venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider tests/test_bilibili_auth_routes.py；新路径应 404 或相关方法缺失。
- [ ] **Step 3: 实现请求模型与 router。** 映射 spec 的 GET status、POST sessions、GET/DELETE sessions/{sid}、POST captcha/password/sms/send/sms/submit/qr/poll/cookie/commit。mode 用 Literal 四值，密码 SecretStr（调用 provider 时才取原值），用户名最长 254、密码最长 512 字符（RSA 超限另拒绝），证明各最长 4096；手机号按大陆 11 位 ASCII 规则，码为 4–8 位 ASCII 数字；Cookie 长度沿用旧入口 4096/128/256。拒绝额外字段，旧入口也经过验证。状态/错误只允许列明字段；B 站校验失败固定文案“登录参数不正确，请检查输入”，不输出 Pydantic input 或原始异常。
- [ ] **Step 4: 实现有界请求体与生命周期。** 中间件只覆盖新前缀与旧 credentials 路径；实际读取 ASGI body 至多 16384 字节后重放给下游，超限即 413，不能仅依赖 Content-Length。重放结束后继续转发真实 receive，使断连检查有效；413 等中间件早退响应也设置三项缓存/引用保护头，保留现有 Host/Origin/写请求头中间件。所有网络/提交路由向 service 传 request.is_disconnected。api.py 组装一次 B 站 service，生命周期关闭先清会话再关采集；没有 source 时固定 404 / SOURCE_UNCONFIGURED。
- [ ] **Step 5: 验证绿灯与安全回归。** 运行 .venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider tests/test_bilibili_auth_routes.py tests/test_api_security.py tests/test_auth_routes.py。覆盖缺头/跨域/DNS rebinding、缺 Content-Length 的分块超限、畸形 JSON/Unicode 数字拒绝、客户端断连不提交、上游 412 映射固定错误、旧通用登录响应保持兼容；全部通过。
- [ ] **Step 6: 保存检查点。** 已有身份时提交 feat: expose protected Bilibili login routes，仅本任务文件。

## Task 5: 默认扫码的 Vue 登录界面

**Files:** Create bilibili-auth-api.js/.test.js、BilibiliLoginPanel.vue/.test.js；Modify BilibiliSourcePanel.vue/.test.js。已有 test-utils/vue.js 与 LoginPanel.test.js 仅作测试模式参考，不重构游戏登录组件。

**Interfaces:**
- Consumes: Task 4 的 API；错误字段 status/errorCode/state/retryAfter。
- Produces API exports: getBilibiliAuthStatus()、createBilibiliSession(mode)、getBilibiliSession(sid)、cancelBilibiliSession(sid)、createBilibiliCaptcha(sid)、submitBilibiliPassword(sid,body)、sendBilibiliSms(sid,body)、submitBilibiliSms(sid,code)、pollBilibiliQr(sid)、importBilibiliCookie(sid,body)、commitBilibiliSession(sid)；均 Promise<object>。请求支持 AbortSignal，等待上限 75000 ms。
- Produces component emits: account-changed；父面板收到后刷新 status，不自动触发真实采集或登录。

- [ ] **Step 1: 写失败测试。** 使用现有内存 Vue renderer、mock fetch/验证码和 node:test 假定时器，不加载外部脚本。test_default_qr_and_single_poll_timer 断言初始 mode=qr、2999ms 不增加 poll、3000ms 增加一次，在途请求不会再发；关闭/卸载后不再轮询。test_switch_discards_stale_results 断言旧响应不改变新面板/账号。API 测试断言所有 URL 使用新前缀、写请求头、同源 credentials 和 75000 ms 超时，pending_save 的状态在异常对象中保留。
- [ ] **Step 2: 确认红灯。** 在 frontend 运行 node --test src/bilibili-auth-api.test.js src/components/BilibiliLoginPanel.test.js src/components/BilibiliSourcePanel.test.js，应因新模块/组件缺失或断言失败。
- [ ] **Step 3: 实现 API 与组件。** 四种方式，默认扫码并展示等待扫描/确认、期限与手动刷新；二维码只用本地 data URL。B 站 Geetest 使用独立 HTTPS 客户端适配 gt/challenge/validate/seccode，不复用 v4 证明、不用 SDK 验证服务器；脚本失败禁用密码/短信操作并显示可恢复提示。发送短信必须用户点击，冷却取后端 retry_after；pending_save 显示“重试保存”，412/额外验证停止当前动作并给固定提示与官方登录页链接。
- [ ] **Step 4: 实现清理与父面板接入。** 使用 generation + AbortController + 单一 setTimeout；成功、切换、取消、关闭清空输入/候选/挑战，尽力 DELETE 旧 sid；超时先 GET 状态而不重放操作。父面板保留现有 configured 判断和采集/审计功能，显示配置存在与已验证状态的区别；不新增其他平台入口。
- [ ] **Step 5: 验证绿灯与界面回归。** 同一命令全部通过，再运行 node --test src/auth-api.test.js src/components/LoginPanel.test.js。加入验证码失败、429/410、非 JSON 错误、成功后账号更新、密码空格保留、前端存储未写、完成/被限制停止轮询、迟到取消/保存结果不覆盖新模式断言。fake cookie/password/code 值不得出现在渲染文本、localStorage/sessionStorage 或 URL；敏感输入只限表单自身。
- [ ] **Step 6: 保存检查点。** 已有身份时提交 feat: add Bilibili three-mode login panel，仅本任务文件。

## Task 6: 回归证据、用户说明与部署交接

**Files:** Modify docs/community-login.md、docs/bilibili-source.md；新增验收记录 docs/bilibili-login-validation.md，仅含版本、测试、模式和安全状态，禁止真实凭据/HTTP 正文。

**Interfaces:** Consumes Tasks 1–5；Produces 可审阅分支/差异、测试记录、构建产物和明确的部署/用户验收状态。

- [ ] **Step 1: 补齐仍缺的失败回归。** 按 spec 检查矩阵补充 test_account_metadata_never_reaches_sdk、test_failed_login_keeps_public_history_and_other_accounts、test_dpapi_legacy_store_and_restart。断言 SDK 只收到六项白名单，旧 bilibili-only 文件可读，失败与取消不改历史/其他账号，重启丢弃未完成会话但保留已保存账号。运行所属 test 文件先红后绿，不写镜像式测试。
- [ ] **Step 2: 运行完整本地验证。** 在隔离目录执行 .venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider -k "not current_user_autostart"；frontend 执行 npm test、npm run build。然后仅在隔离目录按 CI 运行 GA_RUN_RUNTIME_TESTS=1 的 tests/test_powershell_runtime.py -k "not current_user_autostart"，恢复该进程环境变量。结果要求测试无失败、构建退出 0；记录本机 Python 版本，未跑过的 3.11/3.12 CI 组合不声称已通过。网络/沙箱环境故障先诊断并记录，不修改正式服务排障。
- [ ] **Step 3: 更新说明和验证记录。** 说明默认扫码、人工验证、+86、短信冷却、候选待保存、失效后重登、Cookie 兼容、额外验证及 412 限制；保留上游停维护和 PR 未验证边界。记录当前真实验收为未执行，分别列 QR/密码/短信，而不把模拟测试当成真实成功。
- [ ] **Step 4: 完成执行方式对应的审查。** 本会话执行模式在这里由新审查者使用可用最强模型做一次独立的全分支审查；逐任务代理模式按每任务审查并在此做全分支审查。检查凭据替换、迟到结果、Cookie 解析、日志、路由和数据隔离；修正实际问题并重跑受影响检查。git diff --check 与文件清单须无配置/数据/凭据，保留 Git 身份限制，不推送。
- [ ] **Step 5: 提交可评审交付。** 提供差异/分支、相关测试与完整验证结果、构建、限制和剩余真实验收项目；已有身份时提交 docs: describe Bilibili login and validation。当前实施授权不自动成为部署、发短信或登录真实账号授权。
- [ ] **Step 6: 仅在父对话协调部署后执行正式变更。** 先按 spec 第 9 节作同一 Windows 用户的私有一致性备份；检查新工作目录 scripts/start.ps1 -Sandbox -Port 18010、status、stop 的隔离冒烟。原 8010 重启需已取得部署确认，再部署代码/dist 并运行原项目 scripts/restart.ps1、status.ps1、/api/health 和脱敏状态检查；不改自启动。随后由用户自行完成三种登录，若 412 持续则记录未完成真实验收。回退恢复记录的代码/dist，默认保留数据库和有效凭据。

## 自检与执行阶段选择

覆盖映射：spec 1–3 -> Global Constraints/Task 1；spec 4 -> Task 4；spec 5 -> Task 3/5；spec 6 -> Task 1/2/5；spec 7 -> Task 3/4；spec 8 -> 各任务红绿测试/Task 6；spec 9 -> Task 6；spec 10 -> 本计划评审门槛。五项 Review Focus 均有命名测试；公共类型、接口、状态和错误字段在跨任务引用中一致；没有新增范围或占位步骤。

本计划待用户评审并选择执行方式，当前没有产品代码变更或新测试执行：

- Native / 本会话执行：同一执行者按 1–6 顺序完成，每项验证后继续，最后独立审查整个分支；成本和上下文切换较少。
- Subagent-driven / 逐任务代理：每项由新代理实现并由新审查者检查，再做全分支审查；审查更频繁，上下文成本更高。

推荐本会话执行：六项任务共享 provider/service/route 接口，顺序实施更紧凑；最后的独立审查集中检查凭据替换和取消竞态。评审通过并选定方式后才调用对应执行技能；没有选择前不实现。
