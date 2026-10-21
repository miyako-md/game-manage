# 网页更新助手：Windows 与 Linux

这是安装说明，不会因为打开网页自动部署。更新源固定为
`https://github.com/miyako-md/game-manage.git`。默认使用 `refs/heads/main`；
Linux 管理员也可将受保护的助手 JSON 中 `branch` 与云端 TOML 中
`system_update_branch` 同时设为 `codex/cloud-qq-public`。仅允许这两个分支；
来源策略不接受网页参数，助手会独立核对请求、当前发布和实际远端历史。
网页只能提交检查过的目标提交与当前提交，不能指定仓库、分支或命令。

## 支持范围

Windows 使用受管理的 `scripts/start.ps1` / `launch.ps1` 入口。原安装目录必须是干净的 Git 检出；配置与数据保留原位置。数据与凭据存储必须位于原安装的 `data/` 内，且不能穿过链接或目录联接。运行时会启动独立助手，重复启动由 `worker.lock` 排除。现有自定义数据路径不符合范围时，只检查版本，不执行更新。

Linux 必须先由管理员安装助手。支持的布局为：

- `install_root/current` 是唯一允许的发布目录链接，指向 `install_root/releases/<完整提交号>`。
- 当前版本具有干净的 Git 检出，以及匹配源码和前端的 `release.json`。
- API 和 QQ 使用本仓库示例的独立 systemd 服务与 Python 模块入口；不能混用自定义 shell 包装、额外启动/停止钩子或其他进程组模式。
- 云端数据采用 `data_root/identity.db` 与 `data_root/data`；QQ 状态位于 `qq_data_root/state.db`。路径必须是互不重叠的真实目录。
- `cloud.toml` 显式声明 `qq_images_enabled`、`qq_browser_render_enabled`。启用浏览器图片时，还须显式声明既有浏览器与字体的绝对路径；不能依赖助手读取服务环境中的路径覆盖。

仅 wheel、无源码检出或无发布清单的既有安装不会被自动“认领”。应先由管理员按既有发布流程建立可核验版本；助手不猜测线上路径，也不会把未知目录改造成受管理目录。

## 安装 Linux 助手

1. 复制 `updater.example.json` 到管理员拥有的配置位置，例如 `/etc/game-manage-cloud/updater.json`；配置不能由服务用户或其他用户写入。
2. 确认机器已有 Git、`uv`、兼容的 Node.js/npm，以及配置指定的浏览器、字体。助手不会安装系统软件。
3. 管理员先审查安装器、启动引导与 worker/protocol 两个模块，将这份源码置于 root 拥有、其他用户不可写的目录。必须用系统 Python：`/usr/bin/python3 -I -S scripts/system-update-install-linux.py --config /etc/game-manage-cloud/updater.json` 检查布局，不能用任何业务虚拟环境执行 root 安装命令。只有加 `--install` 才会创建构建用户、状态目录、独立助手模块副本、助手服务和 API 的状态目录写权限配置。系统 Python 须为 3.11 或以上。
4. 安装器创建的 API 服务附加配置只允许写共享更新状态目录，不提供写源码或控制 systemd 的权限。管理员须安排一次 API 重启使该沙箱规则生效。
5. 在云端配置启用 `system_update_enabled`，指定 `system_update_install_root` 与 `system_update_state_dir`。确认独立助手心跳正常后再向管理员展示可执行更新的入口。

采用公开工作分支时，当前部署提交必须已同步到该远端分支。网页检查只读取分支最新提交，
提交号不同即提供更新；未发布、领先、分叉或无法核实远端历史时，助手在停止服务前以
`current_not_ancestor` 等原因拒绝，网站不受影响。来源策略不一致时执行更新保持锁定。
配置 `qq_browser_render_dist_path="frontend/dist"` 可让每个受管发布使用自身的渲染资源，
原有浏览器和字体绝对路径继续保留。助手会保留上一发布中受限的公共素材和经过身份核对的
完整字体容器，不复制旧网页入口、凭据或数据库；超过 512 文件或 128 MiB 时要求管理员处理。
构建与隔离检查限制为 384 MiB 内存、64 个任务和半个 CPU 核；准备失败不停止原服务。

助手以 root 负责固定服务启停、发布目录切换及数据恢复。它固定由 `/usr/bin/python3 -I -S` 启动 `install_root/.updater/helper/entry.py`，只加载安装时复制并审查的两个标准库模块；不加载候选版本的 Python、第三方包、`.pth` 或工作目录模块。这个 root 拥有的独立目录对助手服务也只读，下载版本不能更新它。需要升级助手自身时，由管理员停助手、审查新代码并执行单独安装，不能随应用更新自动替换。

下载版本的依赖安装与验证均在随机命名的 systemd 临时服务中运行。构建使用独立低权限 `game-manage-build` 用户，验证使用 API 用户；文件系统默认只读，只开放候选目录和本次临时 HOME。临时服务通过 `BindsTo`、`After`、`PartOf` 绑定助手服务，采用 `KillMode=control-group`。主进程退出、超时或助手停止都会回收整个控制组；助手确认进程净空之后才做最终源码指纹和权限冻结，不能仅靠 chmod 阻止已打开文件描述符的写入。支持主机须使用统一控制组（cgroup v2）。

构建环境不继承业务密钥、代理、Git 凭据或 Vite 覆盖变量；所有助手 Git 命令强制禁用 hooks 与 fsmonitor。运行时健康检查仍连接回环地址，仅使用已验证云端 HTTPS 来源中的 Host，不放宽云端请求边界。

共享状态目录为 `root:<API主组>`、权限 `3770`；永久 `queue.lock` 为 root 拥有、`0660`。API 只创建自己的请求和检查文件。助手状态和心跳的临时文件在原子替换前即设为 root 拥有、`0640`，不会出现替换后短暂不可读的窗口；API 能读取但不能替换。恢复日志和备份位于 `install_root/.updater`、权限 `0700`，不采用网页可写状态中的恢复路径。

## 更新与失败处理

先把新源码与新虚拟环境完整准备到最终发布目录，再停止旧服务。Windows 默认保留 `dev`，检测现有 OCR 后保留 `ocr`；Linux安装 `qq` 与 `qq-render`，额外依赖只接受配置白名单。Python 使用 `uv sync --locked`，前端使用 `npm ci`。同一目标生成前端 `build-info.json` 与发布 `release.json`；虚拟环境准备后不移动路径。

网页进入维护阶段后，助手停止 QQ 和 API，备份数据，再切换发布目录并只启动 API。新 API 在维护期延后后台采集和通知启动，先提供健康与管理员更新状态接口；等待任务会在服务退出时取消。验证新 API 的数据库就绪状态、后端提交和前端提交后，才启动原本启用的 QQ。完成状态公开后，后台任务恢复启动。后台工作是否完成由持久状态决定，不以网页断线或新进程存在作为成功依据。

验证失败且尚未启动 QQ 时，停止新服务、验证并恢复备份、切回原版本、验证原 API，然后恢复原 QQ 状态。QQ 一旦开始启动，可能已经接收消息；此后发生异常会停止服务并标记 `recovery_required`，不会恢复旧去重记录或声称回退成功。没有 QQ 时，也会在公布 `completed` 或 `rolled_back`、允许 API 写入与后台任务恢复之前持久记录不可自动回退边界，避免状态发布末尾故障导致已接收的新数据被恢复覆盖。回退收尾失败时再次尝试停止已恢复服务，不重复恢复数据。恢复状态不确定时，维护状态不会自动解除。

构建失败不影响旧服务。再次尝试时，助手只归档它自己创建且未激活的失败候选目录，再从头准备；未知的同名目录不会删除或采用。旧版本和数据备份不会自动清理。

助手中断时，准备阶段标记失败；停机或激活阶段标记 `recovery_required`，禁止自动重复执行。管理员须先核对私有日志、实际发布链接/Windows活动标记、两个服务状态与备份完整性，再采用既有受控恢复流程。不要仅删除公开 `status.json` 来解除维护状态。

依赖缓存按锁文件区分；锁文件变化时，新缓存先复制最近使用的一份同类缓存（只复制构建用户拥有的普通文件、目录和不跟随的链接），复制失败则从空缓存开始，不影响升级。

### github.com 不可达时的备用取码

助手向 `github.com` 拉取源码重试 3 次仍失败时，才会检查备用来源。`install_root/.updater/inbound/<目标完整提交号>.bundle` 不存在时，照旧以原拉取错误失败；存在时还须同时满足：

1. `inbound` 目录须为 root 拥有、不是链接、组和其他用户不可写（建议 `0700`）；包文件须为 root 拥有的普通文件、不是链接或硬链接（建议 `0400`）。否则以 `unsafe_update_bundle` 失败。
2. 无凭据请求 `https://api.github.com/repos/miyako-md/game-manage/git/ref/heads/<分支>`，返回的分支最新提交必须正好等于目标提交，否则以 `official_main_changed`（不一致）或 `official_head_unavailable`（查不到）失败。

助手先用 `git bundle verify` 核对包（失败为 `invalid_update_bundle`），再要求包内 `refs/heads/<分支>` 正好指向目标提交（否则 `update_bundle_commit_mismatch`），然后从包拉取到私有缓存，后续的官方提交与祖先关系检查不变。Git 拉取时按哈希校验全部对象，所以取到的内容就是 API 确认的提交。成功拉取后包被删除；任务的私有日志与 `status.json` 中 `fetch_source` 记录 `github` 或 `bundle`，不含路径。

管理员在可信的本地检出中制作并上传（示例分支 `codex/cloud-qq-public`）：

```sh
git fetch origin
git rev-parse origin/codex/cloud-qq-public        # 必须等于目标提交 <SHA>
git init --bare /tmp/bundle-src.git
git -C /tmp/bundle-src.git fetch --no-tags "$PWD" refs/remotes/origin/codex/cloud-qq-public:refs/heads/codex/cloud-qq-public
git -C /tmp/bundle-src.git bundle create /tmp/<SHA>.bundle refs/heads/codex/cloud-qq-public
git bundle list-heads /tmp/<SHA>.bundle           # 应为 "<SHA> refs/heads/codex/cloud-qq-public"
scp /tmp/<SHA>.bundle <服务器>:/tmp/
# 在服务器上以 root 安装：
sudo install -d -m 0700 -o root -g root /opt/game-manage-cloud/.updater/inbound
sudo install -m 0400 -o root -g root /tmp/<SHA>.bundle /opt/game-manage-cloud/.updater/inbound/<SHA>.bundle
rm /tmp/<SHA>.bundle
```

然后照常在网页发起更新。`install_root` 以实际助手配置为准。

## 验收边界

仓库测试使用临时 Git 仓库、替代构建命令和隔离数据验证事务，不下载或执行官方最新版，不更新用户安装。Windows 文件锁互斥测试仅在 Windows 的临时文件上运行。另有 `tests/test_system_update_linux_runtime.py`，仅在 Linux、root 且明确设置 `GA_RUN_LINUX_UPDATER_TESTS=1` 时运行：使用临时文件和随机测试服务验证后台持文件描述符子进程的回收、助手生命周期停止、候选 `.pth` 隔离以及 API 用户并发读取状态的权限；不会操作真实 API/QQ 服务或账户。完整 Windows 启停、浏览器运行时权限与操作员首次安装仍需在隔离主机验收后启用。
