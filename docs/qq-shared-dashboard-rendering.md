# QQ 与云端面板共用展示组件

QQ 图片使用 `frontend/qq-render.html`，直接挂载网站的 `OverviewPage`、`CalendarPage`、`GameCard` 及原游戏组件，随同一批 Vue/CSS 构建发布。独立 Python 卡片排版已退役；`presentation.py` 和 `cards.py` 仍负责文字回复及失败回退，不再决定图片布局。

网站正常交互保持原样。截图上下文会原位展开原详情、显示异环全部社区卡池、隐藏无法操作的表单和账号 UID。默认使用网站深色主题，以 540 CSS 像素、2 倍像素密度生成 1080 像素宽的图片；日历使用 1080 CSS 像素和 1 倍密度，以容纳完整 30 天时间轴。它不读取用户浏览器中保存的主题或筛选偏好。

首页按网站规则每游戏取一个授权，终末地优先森空岛；单独寻访仍选鹰角。角色优先默认角色，否则取网站列表首项。日历使用网站默认的滚动 30 天范围；当前活动和未来 168 小时活动仍分别过滤，日期不确定项保留原说明。截图使用分钟级冻结时钟，缓存跨分钟或快照、授权、素材变化时失效。

图片覆盖原组件当前视图；逐抽账本保留网站原来的默认分页及总数，不声称一次展示全部历史。没有已缓存的角色详情时明确显示缺失。图片超过 1 MiB、1600 万像素或查询预算时返回带说明的文字，不退回旧模板、不静默裁切。实际字节上限仍由 `qq_image_max_bytes` 控制。

## 数据与浏览器边界

后端沿用本人账号、角色、授权版本检查，只向截图页面提供脱敏快照及已存在缓存的精确 GET 响应。浏览器没有网站会话、游戏凭据或真实 API 连接；登录、刷新、导入等写请求一律阻断。原网站部分 GET 会触发上游，截图不能代理这些真实路由。生成图片后仍复查 QQ 绑定及每份授权版本，撤销后丢弃结果。

Chromium 进程复用，每次截图创建并关闭独立的临时 context。入口、脚本、CSS 和字体仅从配置的不可变前端发行目录及字体文件读取，通过虚拟 origin 内存提供。其他 HTTP、WebSocket、Service Worker 和导航不放行。角色图标由 Python 的现有 `PublicAssetCache` 下载，继续执行官方 CDN、DNS、TLS、大小和格式限制；页面只能得到本次冻结的净化 PNG。截图与私人数据均无磁盘缓存。

## 部署准备

API 进程新增 `render` 可选依赖；QQ 收发进程仍只接收图片字节。必须一起更新后端、cloud 前端构建和匹配的 Chromium，不能只更新 QQ 机器人包。

1. 使用锁定依赖安装 API 的 `render` extra：`uv sync --locked --extra render`。需要同时跑 QQ 收发进程的环境再加 `--extra qq`。
2. 执行 `python scripts/cloud/build_frontend.py --frontend frontend`。新 dist 必须同时有 cloud `index.html` 和带 `data-qq-render="1"` 的 `qq-render.html`。
3. 在服务用户可读的独立位置安装对应浏览器。示例设置 `PLAYWRIGHT_BROWSERS_PATH=/opt/game-manage-cloud/browser-runtime` 后执行 `python -m playwright install --with-deps chromium --only-shell`。系统依赖安装需要管理员操作；已有离线发行流程应预先准备匹配浏览器与系统库，不在服务启动时下载。
4. 保留 `qq_image_font_path`，使用可读的 Noto CJK 字体；Linux 可安装 `fonts-noto-cjk`。字体不打包进仓库。`runtime.frontend_dist` 同时决定网站和生图使用的发行目录。
5. 在 API service 环境文件设置同一个 `PLAYWRIGHT_BROWSERS_PATH`。现有 `ProtectHome=true` 使开发者 home 中的浏览器缓存不可靠；不要为此移除服务隔离。浏览器需要可写临时目录，现有 `PrivateTmp=true` 提供这一位置。

Ubuntu 的 AppArmor 可能阻止下载的 Chromium 创建用户命名空间，表现为 `No usable sandbox`。按 [Chromium 官方说明](https://chromium.googlesource.com/chromium/src/+/main/docs/security/apparmor-userns-restrictions.md)，管理员应只给实际 headless-shell 二进制的绝对路径增加 `userns` 权限；不能关闭全局 AppArmor 或改用 `--no-sandbox`。例如以下 profile 由管理员写入并加载，升级浏览器 revision 时同步更新路径：

```text
abi <abi/4.0>,
include <tunables/global>
profile game-manage-qq-browser "/opt/game-manage-cloud/browser-runtime/EXACT-REVISION/chrome-headless-shell-linux64/chrome-headless-shell" flags=(unconfined) {
  userns,
}
```

生产浏览器和父目录须由管理员管理、服务账号不可写；profile 应指向 [Playwright 实际使用的 headless shell](https://playwright.dev/python/docs/browsers#chromium-headless-shell)，不能误指向普通 Chrome。CI 在 Ubuntu 24.04 的临时 runner 上按同样方式授权精确二进制路径，保留 `chromium_sandbox=True`。

上线前必须在实际服务用户及 sandbox 下运行合成验证，不使用私人账号：

```sh
python scripts/cloud/verify_qq_render.py \
  --frontend-dist /opt/game-manage-cloud/frontend-releases/REVISION/dist \
  --font /usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc
```

验证可选 `--output` 保存合成预览到一个全新目录。脚本只读给定前端与字体，不打开配置、凭据或游戏数据库，不发送 QQ 消息，不下载远程图标。浏览器 sandbox 启动失败时应修正运行环境；缺浏览器、入口、字体时服务回退文字，不自动降低浏览器隔离。

本地集成验证使用 `GA_RUN_BROWSER_TESTS=1 python -m pytest tests/test_qq_web_rendering.py`；须先完成 cloud 构建和浏览器安装。CI 的 Linux 浏览器任务验证真实 Vue、上下文隔离、请求限制、动态素材和图像预算，Windows 任务保留其他回归。这里的测试与预览不代表线上发布或真实 QQ 收图已通过。
