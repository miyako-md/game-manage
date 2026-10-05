# B站三种登录验证记录

日期：2026-10-02。主机：LAPTOP-MIYAKO0721。基础提交：`d3f7b9354d9d5f38c295604268e5632fa734b5e1`。独立分支：`feat/bilibili-login`；未合并、未推送、未部署到现有 8010 服务。

环境：Windows，Python 3.12.10，锁定 SDK `bilibili-api-python` 17.4.2，新增直接依赖 `qrcode[pil]>=8.2,<9`。未执行 Python 3.11 或其他操作系统矩阵。正常 Windows 用户测试仅用假凭据和临时数据库；沙箱令牌无法使用当前用户 DPAPI，属于环境差异，未修改加密实现或系统安全设置。

## 实际支持与验收边界

| 登录方式 | 协议/模拟验证 | 真实账号验收 |
| --- | --- | --- |
| 扫码 | 本地二维码、等待状态、旧查询 Cookie、新跨域 Set-Cookie、跳转白名单、UID 验证、只消费一次 | 未执行；本机只读登录请求曾返回 412 |
| 账号密码 | RSA 盐值加密与原始密码字节、Geetest v3、响应 Cookie、额外验证阻断、UID 验证 | 未执行；未请求或读取真实密码 |
| 手机号验证码 | +86 手机号绑定、验证票据、短信冷却/总限额、验证码保留前导零、额外验证阻断 | 未执行；未发短信、未完成 CAPTCHA |
| Cookie 导入 | 旧接口也验证账号后保存、支持仅 SESSDATA、失败保留原账号 | 仅假凭据模拟；未读取真实 Cookie |

这里没有宣称B站官方开放 API 支持上述网页登录。参考的是安装 SDK 的网页协议与公开源码；上游 [bilibili-api](https://github.com/Nemo2011/bilibili-api) 已宣布于 2026-07-06 停止维护。公开 [二维码修复 PR #27](https://github.com/public-clis/bilibili-cli/pull/27) 尚未合并，不能替代真实账号验收，也不能仅按 SDK 版本判断接口兼容性。

## 自动化证据

日志与执行记录保存在忽略目录 `.superpowers/sdd/2026-10-02-bilibili-login/`。协议测试均拦截网络；应用接口使用临时数据库、模拟 provider 和假凭据。DPAPI 测试仅验证加密、原子替换和旧格式重载。

- 正常用户后端基线：872 passed，3 skipped，1 deselected（排除开机启动设置）。前端基线：256 passed。
- 登录 provider：38 passed，包括 DEBUG/INFO 网络日志票据脱敏回归。
- 会话、存储、采集集成：相关测试已通过，另加入重启、元数据隔离、坏存储保留回归。
- 登录路由、安全边界与原有游戏登录：67 passed。
- 全量前端：265 passed。`npm run build` 成功，Vite 提示已有主包超过 500 kB。
- 全量后端：943 passed，3 skipped，1 deselected，242.30 秒。独立随机端口 Windows 进程测试：2 passed，1 deselected，18.55 秒；未修改开机启动设置。
- 独立审查：5 个 Important、1 个 Minor、无 Critical。一次修复通过 RED→GREEN 回归覆盖 Geetest v3 回调、闲置清理、手机号倒计时、短信纠错重试、混合 Cookie 冲突与空 userinfo。修复后最终后端：951 passed、3 skipped、1 deselected（242.42 秒）；前端：267 passed；重新构建成功；隔离进程：2 passed、1 deselected（16.09 秒）。三个全量跳过项为两个 opt-in 隔离进程测试和一个 Windows 符号链接权限测试；隔离进程另行显式启用通过。

## 后续部署与用户验收

当前变更仅在独立工作区，现有配置、数据和 8010 服务保持原状。父对话协调部署审批：同一 Windows 用户先私有备份配置、数据库及加密凭据，再合并代码与构建产物并重启既有服务；回退代码时保留数据与有效凭据。用户自行输入账号、完成验证码和扫码，逐项确认三种方式及采集恢复。412 或额外风控应记录为暂时无法完成真实验收，不绕过。

## 最终交付状态

独立审查修复均有先失败后通过的回归，未进行第二轮重复审查。测试命令为 `.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider -k "not current_user_autostart"`（正常 Windows 用户、独立临时基目录）、`npm test`、`npm run build`，及 `GA_RUN_RUNTIME_TESTS=1` 下运行 `tests/test_powershell_runtime.py -k "not current_user_autostart"`。

Git 作者未配置，因此保持未提交工作区，不擅自设置身份。交付差异排除已批准且父工作区已有的 spec/plan，已在原始提交的干净副本验证 `git apply --check`。交付包包含源代码、测试、说明与构建产物，不含用户配置、数据库或凭据。原项目仍在 main、基础提交不变，仅保留之前已批准的两份未跟踪设计/计划文件。

Geetest 精确 challenge 后缀语义未获官方文档证实；前端不再强行比较 getValidate 的 challenge。采用安装 SDK 的行为，仅消费 validate/seccode，服务端保留并绑定原始 challenge/token；generation、120 秒和一次性消费仍生效。最终真实 CAPTCHA/账号验收仍是后续事项。
