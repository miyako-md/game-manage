# 前端布局与动效

保持 PR #8 首次提交的页面结构与紧凑信息排布，视觉细节参考 [option-pro](https://github.com/iroha1145/option-pro) 的纸面样式：冷灰底色、白色卡片、细边框、12px 圆角和轻阴影。深色主题沿用同一套层次；标题、导航、筛选控件和游戏页头统一使用克制的字重与间距。

游戏主题色沿用 `GAME_STYLE` 与日夜主题变量。选中态、焦点环、进度条和详情标题使用当前游戏的颜色；正文保持中性色和稳定的可读性。

## 交互约定

- **导航与标签**：背景指示器位于独立层级，文字和图标始终在其上方。左侧菜单参考 Cloud-Monitor 的选中滑块投影，使用随游戏主题色变化的柔和阴影；侧栏边缘增加轻阴影区分内容区。窄屏标签条在选择变化或容器变窄时，将被遮住的选中项滚入视野；不滚动整个页面，也不打断用户手动浏览标签。
- **详情面板**：保留鸣潮与异环原有的居中弹窗、各自的尺寸与样式，手机上也保留四周留白。两者仅共用模态生命周期与动效逻辑。打开约 250ms，关闭约 150ms，位移 8px；关闭动画结束后才移除弹窗、解锁滚动并恢复入口焦点。动画事件缺失时，220ms 后仍会完成关闭；组件提前卸载会取消等待。
- **总览卡片**：保留原来的紧凑排版，数字和说明并列，账号与更新时间同一行。进度条平滑更新，悬停高光不覆盖文字。
- **活动日历**：活动名称与状态显示在细时间条上方，日期比例不变。移除斜纹和文字阴影；短活动保留完整标签，右侧活动标签向左展开。卡片按内容高度显示，较多活动时滚动，避免固定高度带来的空白。日期标记与裁剪区间仍使用原有数据语义。关闭详情或按 Escape 后，焦点回到原活动；详情滚动遵守减少动态效果偏好。
- **减少动态效果**：系统开启 `prefers-reduced-motion` 后，关闭动效、标签平滑滚动和指针跟随，弹窗直接关闭。功能和当前选中状态保持可用。
- **动画范围**：数值和页面内容无需等待动画完成才能阅读。动效绑定到用户操作或内容变化，卸载时清理观察器、事件和待执行帧。

## 参考与取舍

2026-09-28 浏览了这些参考。下面区分实际落地的交互、节奏参考与仅浏览过的网站；没有复制参考站的图片或引入新的运行时动效库。

| 来源 | 当前保留的实现与边界 |
| --- | --- |
| [60fps — Tabs](https://60fps.design/shots/filter/tabs) / [Airbnb 标签示例](https://60fps.design/shots/airbnb-tactile-tab-button-interaction) | 选中项自动滚入横向标签条的可见区域；只在选中项或容器宽度变化时调整，不覆盖用户的手动滚动。代码：`motion.js` 的 `revealControl`、`vGlide`。滑动选中背景本身在首版 PR 中已有。 |
| [Design Spells — Smooth sheet transitions](https://designspells.com/spells/smooth-sheet-transitions-in-sudoku-a-day) | 鸣潮与异环详情弹窗增加进入 / 退出过渡，关闭后恢复焦点和滚动。当前使用 250ms / 150ms、8px 位移。手机底部面板的改版已撤回，保留原有居中弹窗。代码：`use-dialog.js`、`motion.css` 的 `.t-dialog`。 |
| [Zajno Motion](https://motion.zajno.com/) | 参考快起慢停、小幅位移和开合节奏，用于上面弹窗的动效调校；共享缓动变量沿用已有实现，没有搬入独立场景或组件。 |
| [Viewport UI](https://viewport-ui.design/) / [Motion](https://www.motionin.design/) | 仅补充交互思路。悬停、按压反馈和减少动态效果在首版 PR 中已有，不能算成这两个网站各自带来的新增功能。 |
| [Seesaw](https://www.seesaw.website/) / [Recent](https://recent.design/) / [Inspora](https://www.inspora.design/) / [posts.design](https://posts.design/) | 浏览过的排版与信息层次参考，没有独立移植组件。当前可见的整体视觉样式主要按后续指定的 option-pro 调整。 |
| [Mobbin animations](https://mobbin.com/discover/apps/ios/animations) | 未登录只能查看公开介绍，未采用受限动画内容。 |

此外，最初的 [Obsidian UI](https://www.obsidianui.dev/docs/split-showcase) 用于参考卡片悬停高光和微小抬升；最初的圆角形变在后续纸面风格调整中已移除。[option-pro](https://github.com/iroha1145/option-pro) 是当前整体视觉的主要参考，直接对照其 `frontend-src/src/index.css` 与 `MonthCalendar.tsx` 的表面、标题、日期和控件样式，在现有 Vue 组件内实现。

日历日期头使用固定三行布局：星期、日期数字、今天标注。三行留出独立空间，日期数字使用等宽字体，中文使用界面字体；普通日期与选中日期保持相同高度，避免负边距与绝对定位造成重叠。

## 验证

在 `frontend` 运行 `npm test` 和 `npm run build`。DOM 回归覆盖动态 class 更新后的导航层级、快速切换、横向滚动、减少动态效果、弹窗关闭与卸载清理。现有详情测试继续验证按需挂载、关闭和账号切换。

浏览器使用模拟快照检查桌面及手机布局、日夜主题、原生模态状态、Escape、焦点恢复和横向溢出；它验证界面行为，不依赖私人游戏账号。
