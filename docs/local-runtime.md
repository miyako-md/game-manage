# Windows 本地运行

在项目根目录安装好 `.venv` 后，执行前端构建，再启动：

```powershell
cd frontend
npm run build
cd ..
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/start.ps1
```

浏览器打开 `http://127.0.0.1:8010`。这个端口同时提供静态网页和 API，仅监听 IPv4 本机地址。生产启动不创建 Vite 进程；5173 的开发模式仍可单独使用。缺少 `frontend/dist/index.html` 时启动脚本提示警告，API 可继续运行，网页需要构建后重启。

## 管理命令

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/status.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/restart.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/stop.ps1
```

重复启动已健康的受管服务会复用现有进程。重复停止已停止的服务成功返回。脚本固定工作目录为脚本所在项目根目录，所以从其他目录启动也不会读取另一份配置。生产模式继续使用项目 `config.toml`、已有环境配置、数据库和凭据库，保持既有采集频率；没有额外的开机补采集请求。

脚本通过项目路径、每次启动的随机标识、实际 Python PID、进程创建时间和解释器路径验证归属，防止 Windows 虚拟环境启动器子进程或 PID 复用导致误判。健康检查同时确认 `/api/health` 返回 `service=game-assistant`、`status=ok`，并确认监听端口归该进程所有。已有非受管进程占用 8010 时启动失败且保留该进程；手工运行的旧服务需要先确认归属并自行退出，再交给脚本。不会依据占用端口直接终止任何进程。

启停操作使用互斥文件锁。`restart.ps1` 在同一把锁内完成停止和启动。停止时先写入绑定本次启动标识的本地 `stop.json`，运行器收到后要求 Uvicorn 优雅退出，让进行中的请求和应用关闭逻辑有机会完成；没有对外的停止 API。脚本等待 10 秒，超时后重新验证进程身份，再使用进程句柄强制终止，此时未完成的请求会中断。状态或创建时间校验失败时脚本拒绝停止，需要人工核对后处理记录。

## 日志与运行记录

路径均在项目 `data/runtime/`（Git 忽略）：

- `service.json`：PID、进程创建时间、项目路径、解释器路径和本次启动标识；没有配置凭据。
- `ready.json`：Python 运行器的实际 PID 握手。
- `stop.json`：只对匹配本次启动标识的进程有效的优雅退出请求，停止后清除。
- `service.lock`：命令互斥锁，空文件保留是正常现象。
- `service.log`、`service.log.1` 至 `.3`：UTF-8 滚动日志，每份约 2 MiB，总计约 8 MiB；发生单条超长消息时可短暂超出分片大小。

Python 标准输出/错误统一进入滚动日志，不记录 HTTP 访问 URL，避免查询参数出现在访问日志中。HTTPX/HTTPCore 日志门槛设为 WARNING，避免信息级日志记录 ServerChan URL 路径中的推送密钥。通知失败只记录异常类型、HTTP 状态和安全数值状态码，不记录原始响应或异常堆栈。启动阶段的配置错误仅写异常类别，不打印设置值。身份验证和状态输出不展示凭据。若 Python 本身无法启动或运行器文件损坏，可能尚未生成日志；先检查 `.venv` 和依赖。

## 当前用户登录后启动

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/autostart.ps1 -Status
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/autostart.ps1 -Enable
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/autostart.ps1 -Disable
```

使用当前用户 Windows Startup 文件夹的 `GameAssistant-<项目路径哈希>.lnk`；无需管理员权限。该快捷方式隐藏执行项目 `start.ps1`，仅在用户登录后生效，不是系统启动服务。启用/停用均可重复执行，脚本重新读取落盘快捷方式确认结果；同名条目归属不一致时保留原条目并报错。启用不会立即启动服务，停用不会停止当前服务。移动项目目录前先从原目录停用，再在新目录启用。

本次交付默认关闭登录自启动。自动测试只会对初始关闭的条目启用后撤销；如发现原本已启用，则跳过该项以保留用户设置。注册/撤销测试不等同于实际注销并重新登录验收。

## 隔离验证

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/start.ps1 -Sandbox -Port 18010
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/status.ps1 -Sandbox -Port 18010
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/restart.ps1 -Sandbox -Port 18010
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/stop.ps1 -Sandbox -Port 18010

$env:GA_RUN_RUNTIME_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest tests/test_powershell_runtime.py -q
Remove-Item Env:GA_RUN_RUNTIME_TESTS
```

隔离模式要求使用 8010 之外的端口，数据库和记录放在 `data/runtime/sandbox-<端口>/`。所有设置显式使用无凭据默认值，忽略项目配置和 `GA_*` 环境值，关闭所有适配器与调度器，不访问上游、不发送通知。正式模式不支持改端口；隔离模式不会改变正式服务设置。静态页面仍使用项目构建产物。

静态托管路由在 API 注册后安装。未知 `/api` 路径、缺失资源和目录穿越返回 404；前端页面导航回退 `index.html`，页面入口要求重新验证缓存。静态软链接若指向构建目录外则拒绝访问；Windows 未开启相应权限时，软链接用例会明确跳过。
