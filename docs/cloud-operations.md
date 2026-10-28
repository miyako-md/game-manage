# 云端部署与恢复准备

状态：用户单独批准后，`https://game.rekibot.cloud` 公网站点已启用，可信 TLS 和访问边界通过；仍处手动刷新试运行。鸣潮、异环真实授权和 Linux QQ 同源查询、真实同机备份恢复均已验证；手机流量人工登录、自动采集、开机策略及 24 小时观察尚未完成，详见[实现验收记录](cloud-implementation-acceptance.md)。域名备案状态来自操作者确认；原 LOLhelper 保持独立，本机单用户入口继续使用 `127.0.0.1:8010`。合成结果不能证明服务器容量。

## 独立运行与配置

使用独立发布目录 `/opt/game-manage-cloud/releases/<revision>`，`current` 指向已验收版本；不要修改 LOLhelper 的目录、配置、密钥、端口或现有 `sync.rekibot.cloud`/`:8443` Caddy 站点。API 使用 `game-manage-cloud` 用户，QQ 使用 `game-manage-qq` 用户；两个用户没有彼此数据目录写权限。API 只有一个 worker 和一个 OS 锁保护的调度器。QQ 不运行游戏调度器。

先检查拟用的回环端口 `ss -ltnp`；模板 API 为 `127.0.0.1:8020`。端口在 `[runtime].port`、Caddy 上游、`QQ_INTERNAL_URL` 三处同步配置。服务只能绑定回环地址；外网通过新 Caddy 站点进入。`QQ_INTERNAL_HOST=game.rekibot.cloud` 提供应用 Host 校验要求的 authority，网络连接仍直达回环。Caddy 明确拒绝 `/internal` 和 `/internal/*`，其中 QQ bearer 接口和运维检查不能从外网访问。

操作者在独立发布环境安装 Python 项目及 `qq` extra（只有启用 QQ 时），前端按锁文件执行 `npm ci`。不要安装到本地正式使用的虚拟环境。将 `deploy/cloud/cloud.example.toml` 复制到操作者专用位置 `/etc/game-manage-cloud/cloud.toml` 并设置所有实际路径；示例不是可直接启用的配置，外置密钥和前端产物必须先准备好。运行入口不会自动读取旧 `config.toml`、导入本地凭据或生成替代密钥。

```sh
python scripts/cloud/build_frontend.py --frontend frontend
python -m game_assistant.cloud_runtime --config /etc/game-manage-cloud/cloud.toml --check
python -m game_assistant.cloud_runtime --config /etc/game-manage-cloud/cloud.toml
```

前端构建工具显式设置 `VITE_SERVICE_MODE=cloud`，成功后只在构建产物 index 添加模式标记。专用静态 helper 只公开实际 dist 文件的精确路径，拒绝符号链接、数据目录和未知 artifact；JSON 仅允许已知图标来源 `game-icons/sources.json` 与不含私密配置的版本标记 `build-info.json`。它不公开配置、密钥、数据库或源码，不使用 catch-all 覆盖运行时账户 API。

管理员可在网页右上角打开“系统更新”，检查官方主分支（main）。执行更新需先安装独立助手，配置和首次接入步骤见[网页更新助手说明](../deploy/cloud/updater-setup.md)。普通网站用户无此入口和接口权限；网站进程不获得写程序目录或启停服务的权限。现有无 Git 发布记录的安装需先经人工建立可核验版本，不会直接改造线上目录。

外置 grant 密钥必须是 32 字节随机二进制，Linux 文件 owner 为 API 用户，权限 `0600`，父目录仅授权该用户。例：在已创建、授权的专用密钥目录中使用下面命令；文件独占创建，已有密钥不会覆盖。不要把密钥内容写入配置、日志或报告。

```sh
python -c 'import os; f=os.open("/etc/game-manage-cloud/grants.key",os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600); os.write(f,os.urandom(32)); os.close(f)'
```

网站初始管理员使用已有 identity 管理 CLI／服务，在专用数据库初始化；密码、验证码、人机验证由操作者处理。QQ AppID、AppSecret、allowlist 和独立服务 token 使用 owner-only 环境文件，参照 `service.env.example` 与 `qq.env.example`，填好后的文件不得提交。API `GA_QQ_SERVICE_TOKEN` 与 QQ `QQ_SERVICE_TOKEN` 必须相同，但不复用游戏授权密钥。网站 Cookie 不能替代 QQ bearer。镜像功能默认关闭；若后续进行受控图片验收，可安装 Ubuntu `fonts-noto-cjk` 并通过 `GA_QQ_IMAGE_FONT_PATH` 指向系统 NotoSansCJK 字体，禁止打包 Windows 字体。真实图片上传和峰值内存尚未验证，不应因此打开生产图片功能。

鸣潮开始登录需要查询服务器的实际出口公网 IP。运营者可在云端 TOML 顶层设置 `wuwa_login_public_ip_url`，默认 `https://api.ipify.org`；当前允许 `https://api64.ipify.org`（IPv4/IPv6）及 `https://checkip.amazonaws.com`。值不带 query（包括 `?format=json`）、fragment 或用户凭据；仅选择服务器已实测可达且返回纯文本有效公网 IP 的来源。HTTPS 证书正常校验，单次超时 10 秒，无自动回退、重试或代入 SSH 地址；无效／私网结果会拒绝初始化。该选项只来自运营者配置，网站登录请求不能指定查询 URL，不改变手机号、极验或短信流程。普通 wheel 安装须在新 release 中重新安装包并核对实际导入版本，不能只改发布目录源码假设已生效。

采集频率（2026-10-21 起）：公共来源，即 B 站官方动态、库街区/塔吉多公告、终末地官网资讯和异环配队推荐，由 `cloud_public_poll_seconds` 控制，默认 21600 秒（每 6 小时一次）；终末地官网另有 6 小时缓存，网页读取不会额外访问官网。私人数据（体力等）仍按 `cloud_private_poll_seconds`（900 秒），不受影响。资讯和日历的“已过期”判断按 2 倍采集周期计，6 小时周期内的数据不会被标为过期。服务器 TOML 若显式写了 `cloud_public_poll_seconds = 600`，须改为 `21600` 或删除该行才生效；API 重启后会立即采集一轮，之后按周期执行。需要立即更新时，管理员在「今日总览」点「采集与回补」：每个游戏立即排一次公共采集（终末地强制刷新官网缓存，B 站回补近 60 天；B 站处于失败退避时跳过 B 站并在进度中注明），同时刷新管理员本人各账号的私人数据；同一游戏已在采集时合并，不重复排队，全站 5 分钟内只能触发一次。

每日攻略检查（2026-10-22，M9）：调度器键 `('guides','daily')`，北京时间每天 `cloud_guide_check_time`（默认 `"05:30"`，`HH:MM`，启动时校验）后运行一次。顺序：鸣潮全角色（46 个静态条目 + 默认权重表中无静态条目的角色；角色间隔 3 秒；只在首选帖变化时提炼，每轮最多 8 个）→ 深塔（到期才查）→ 异环 2 个收录帖（缓存超过 24 小时才请求）→ 异环攻略作者轩儿Zero 的帖子列表（塔吉多免登录接口 `/bbs/wapi/getUserPostList?uid=10208854&count=20`，24 小时缓存，1 次请求）：标题为“异环角色 | V… <角色>培养攻略一图流”或“异环V…全角色养成一图流”、且帖子 ID 大于目录对应来源的帖子列为新帖（2026-10-28 起）。新帖不自动提炼：目录里没有的角色在攻略页先展示新帖原图（标“新帖 · 仅原图”），已有角色提示“作者已发布更新版本”。使用独立供应者信号量 `kurobbs_public`，不占用私人轮询的全局并发；复用 `public_tools` 上同一组攻略服务实例，与管理员按钮共用锁。运行记录在 `public.wuwa-guides.sqlite3` 的 `guide_runs` 表，重启不重跑当天已开始的时段；API 关停时取消进行中的检查并记为 `stopped`（`stop_code=shutdown`）。库街区 429/403 立即停止鸣潮部分并跳过深塔，日志 `guide_job_stopped code=http:429`；每轮结束一行 `guide_job_finished outcome=ok|partial|stopped|failed checked=… extracted=… failed=…`，不含玩家标识。该键**不要写进服务器 TOML**：默认值即生效，旧版本回滚时会拒绝未知键；确需改时间再显式加一行。

管理员接口（管理员 + CSRF，与其他 `/api/admin/*` 一致）：`GET /api/admin/guides` 返回任务状态（`idle/queued/running`、上次运行、下次时间、冷却剩余秒数）、鸣潮名单检查覆盖、待处理新帖、提炼失败与检索失败码、深塔当期覆盖与失败码、异环原帖读取时间/过期/失败/摘要变化、作者帖子列表检查时间与新攻略帖（`nte.author_checked_at`、`nte.new_posts`）；鸣潮待处理新帖带 `state`（`not_extracted` 未提炼 / `extracted_empty` 已提炼但没识别到内容，原帖是图片且线上无 OCR / `awaiting_review` 有静态攻略、提炼结果待人工核对）、原帖链接，未提炼的可在卡片上直接调用 `POST /api/admin/wuwa/guides/updates/extract` 立即提炼。以上只读缓存不访问上游；`POST /api/admin/guides/check` 把同一后台任务立即排队，已排队或运行中时合并（202 `{"state":"queued"|"merged","retry_after":600}`），全站 10 分钟冷却（429 `guide_check_cooldown` + `Retry-After`），调度器未运行时 503 `scheduler_unavailable`。

`game-manage.service` 与 `game-manage-qq.service` 是待审核模板。只在新独立路径安装；检查 `systemd-analyze verify` 后再启用。资源初值：API `MemoryHigh=512M/MemoryMax=768M`，QQ `192M/256M`；CPU 配额分别 150%/50%，失败最多 300 秒内重启 3 次。OOM 停止后查看失败并告警，不能无限重启。数值是试运行初值，不是容量结论。`journald-cloud.conf` 安装到专用 `/etc/systemd/journald@game-manage-cloud.conf.d/limits.conf`，namespace 日志保留最多 64MiB/7 天，运行时最多 16MiB；不调整现有服务全局日志策略。

合并 Caddy 片段到操作者审核的新配置后先运行 `caddy validate --config <reviewed-config>`。只有校验成功、域名解析/TLS 实测及明确切换授权后才 reload；模板不得替换整份服务器配置。`__Host-ga_session`/preauth 为 Secure、HTTPOnly、SameSite=Lax，无 Domain、Path=/，要求真实 HTTPS。HTTP 页面不能作为网站登录验收。

## 在线备份与新目录恢复

已有 identity CLI 只读取 Settings 键，不能直接读取含 `[runtime]` 的运行配置。使用 `identity-admin.example.toml` 另建操作者配置，确保 cloud_db_path 与运行配置完全相同且为绝对路径，然后执行 `python -m game_assistant.identity.cli --config /etc/game-manage-cloud/identity-admin.toml bootstrap-admin`。管理员口令由终端 getpass 输入；不要交给代理或写入脚本。

在线备份使用 SQLite backup API，支持源 WAL 正在写入；不复制主库文件代替在线备份，也不复制 WAL/SHM。副本转换为 DELETE journal 以形成独立可读文件。清单包含身份库、snapshots、private_scope 验证的全部私人账本、已知公共数据库和静态迁移报告/manifest。未知数据文件、未来身份版本、符号链接、重叠目录或已有目标会失败；日志和 scheduler 锁不备份。若出现公共 credentials sidefile，工具拒绝而不静默丢失，需先核对云端隔离配置。QQ 独立进程 state.db 属于 replay/传输状态，另做在线 SQLite 备份；不包含游戏凭据，也不能替代中央库备份。

```sh
python scripts/cloud/backup.py --source /var/lib/game-manage-cloud/data --identity /var/lib/game-manage-cloud/identity.db --destination /operator-chosen-backup/new-backup-id --key /etc/game-manage-cloud/grants.key
python scripts/cloud/restore.py --source /operator-chosen-backup/new-backup-id --destination /var/lib/game-manage-restore/new-drill-id --key /operator-separate-key-restore/grants.key --live-root /var/lib/game-manage-cloud/data
```

目标目录必须尚不存在且不与输入或密钥路径重叠。恢复生成 `identity.db`、`data/*` 与脱敏 restore-report，须新建配置指向恢复目录，原运行库和备份原件保持不变。恢复核对版本、完整文件清单、SHA-256、SQLite quick_check、密钥指纹，并对全部启用 grant 实际 AES-GCM 解密验证；没有 active grant 明确报告 `no_active_grants`，不伪称有凭据可读。清单不是数字签名；备份及清单必须放在可信、访问受控的存储。

一致性范围是**逐文件在线一致性**，manifest 固定记录 `whole_system_snapshot=false`。不同 SQLite 文件之间没有原子跨库事务；并发撤销／刷新／建分片可能令跨文件状态不同时。工具检测 inventory 变化，但不能证明跨库同一时点。需要最终切换快照时先停止 API 和 QQ／所有写入者，记录停写证据，再备份并恢复演练；工具不因一个命令参数就声称整系统快照。中断的 `.b-*`/`.r-*` 暂存目录不会发布，保留供操作者检查，不自动删除或当成成功重用。

每日备份及保留 7 日、4 周由操作者安排到选定目的地；工具不自动删除旧备份。**数据备份位置、密钥单独备份位置、异机副本、访问权限和恢复联系人必须在生产切换前确定。**同机备份不算灾难恢复验收。密钥不包含在数据备份中，不得丢失或与公网产物一起发布。

## 合成 HTTPS 与验收

以下只操作新建合成目录，账号数据、授权、资讯与日期全部为 fixture；真实社区授权和 QQ 内部发送路径被拒绝，轮询仅允许手动触发本地缓存 adapter，没有周期采集。localhost 证书由已安装的 cryptography 生成，仅 7 天有效且未加入全局信任。浏览器须确认该本机测试证书；公网必须使用正常可信 TLS。为浏览器验收新建 2 用户目录，为 ASGI 负载新建 20 用户目录，不能指向生产数据。

```powershell
$env:PYTHONPATH='C:/Zcode/game-manage-cloud-qq/src;C:/Zcode/game-manage/.venv/Lib/site-packages'
& '.venv/Scripts/python.exe' scripts/cloud/build_frontend.py --frontend frontend
& '.venv/Scripts/python.exe' scripts/cloud/qa_fixture.py create --destination '.superpowers/sdd/2026-10-12-cloud-qq-dashboard/task12-browser-qa' --frontend-dist frontend/dist --users 2 --port 8446
& '.venv/Scripts/python.exe' scripts/cloud/qa_fixture.py serve --destination '.superpowers/sdd/2026-10-12-cloud-qq-dashboard/task12-browser-qa'
```

访问 `https://localhost:8446`，合成账号 `qa_user_01`/`qa_user_02`，共用仅测试密码 `Synthetic-test-password-01`。创建命令只显示这些合成登录信息；绝不显示密钥。创建已有目录会拒绝，不要重建覆盖已生成实例。退出服务用 Ctrl+C。

```sh
python scripts/cloud/qa_fixture.py create --destination <new-ignored-20-user-dir> --users 20 --port 8445
python scripts/cloud/verify.py --source <new-ignored-20-user-dir> --requests 600 --output <new-result-json>
```

verify 只接受 synthetic marker；轮流测 20 用户 × 3 游戏缓存查询、真实会话隔离（非本人统一 404）、真实 scheduler 刷新合并。数据均在本地，无真实上游压力。P95 <2 秒、HTTP 错误率 <1% 是初始提议指标；本地 ASGI 延迟不含公网/TLS、真实 QQ、客户端渲染，不能外推 Ubuntu 2 核约 2GB 的容量、图片峰值或 24 小时稳定性。正式负载验收还需分阶段增加并发并记录实际 Linux 内存、写锁、OOM、原 LOLhelper 健康及 QQ 端到端延迟。

发布门槛：Linux 安装／启动／外置密钥解密／关停与重启；完整后端及前端回归；至少两名真实用户、两设备、手机流量验证归属、会话撤销、授权复用和来源日期；真实 QQ 官方沙箱到业务查询；受控图片测试；24 小时资源与原服务观察。上述状态由根任务采集证据，不通过合成工具自动标为完成。

## 切换与回退

### 2026-10-13 当前试运行状态

公网 `https://game.rekibot.cloud` 已启用且用户手机流量登录、鸣潮/异环查询和公共公告/日历显示通过。后端独立 release 为 `e20e18285e3eeb8de0b2ebbe55b899f69d8476c7`，前端保持 `4828931`；旧 LOLhelper 和原 Caddy 站点保持。周期从 01:52:43（UTC+8）启用，单 worker、单 OS 锁、全局/来源并发 1，私人 900 秒、公共 600 秒；终末地公共源自身缓存 4 小时。

有限观察从 10 月 13 日 01:54:49（UTC+8）到 10 月 14 日约 01:54:51，每 5 分钟采样。transient unit 为 `game-manage-cloud-trial-observe-20261013T012533-7368cc76.service`，结果目录 `/var/lib/game-manage-cloud-trial-observation/20261013T012533-7368cc76/logs`；停止观察只能停止该独立 unit，不停止业务服务。观察器到期自行结束，助手每小时跟进 ID `24` 在终态审查后暂停。无结果或样本不足须记为中断/未完成，不能按时间推定通过。详细边界见 [试运行准备与观察](cloud-trial-readiness.md) 和 [验收记录](cloud-implementation-acceptance.md)。

保留版本化程序、锁文件、迁移报告和原库最终一致性备份。正式 QQ 审核、DNS/TLS启用与公网访问切换须材料齐备后单独确认。切换前停写旧系统；新库启用后新增记录独立导出核对。回退先停新进程，使用匹配旧 schema 的旧程序与旧库备份，不让旧程序读取新 schema，不自动将新记录混入旧库。不删除旧发布或旧备份。解除 QQ 绑定／旧会话及迁移后的游戏重新授权要求按对应迁移报告执行；任何降级必须记录。
