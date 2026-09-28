# 前端布局与动效

游戏主题色沿用 `GAME_STYLE` 与日夜主题变量。选中态、焦点环、进度条和详情标题使用当前游戏的颜色；正文保持中性色和稳定的可读性。

## 交互约定

- **导航与标签**：背景指示器位于独立层级，文字和图标始终在其上方。窄屏标签条在选择变化或容器变窄时，将被遮住的选中项滚入视野；不滚动整个页面，也不打断用户手动浏览标签。
- **详情面板**：鸣潮与异环共用原生 `dialog` 容器。桌面居中，640px 以下贴底，内容独立滚动。打开约 250ms，关闭约 150ms；关闭动画结束后才移除弹窗、解锁滚动并恢复入口焦点。动画事件缺失时，220ms 后仍会完成关闭；组件提前卸载会取消等待。
- **总览卡片**：游戏身份、主要数字、数据说明、进度、账号与更新时间分层排列。说明占用完整行，长昵称可以截断，更新时间独立显示。悬停高光不覆盖文字。
- **减少动态效果**：系统开启 `prefers-reduced-motion` 后，关闭动效、标签平滑滚动和指针跟随，弹窗直接关闭。功能和当前选中状态保持可用。
- **动画范围**：数值和页面内容无需等待动画完成才能阅读。动效绑定到用户操作或内容变化，卸载时清理观察器、事件和待执行帧。

## 参考与取舍

2026-09-28 查看了以下公开参考，采用交互原则，在现有 Vue 代码中实现；没有复制参考站的图片或引入新的运行时动效库。

- [60fps — Tabs](https://60fps.design/shots/filter/tabs)：选中反馈与横向标签可见性；[Airbnb 标签示例](https://60fps.design/shots/airbnb-tactile-tab-button-interaction)用于参考操作和反馈的连续性。
- [Design Spells — Smooth sheet transitions](https://designspells.com/spells/smooth-sheet-transitions-in-sudoku-a-day)：移动端详情面板的开合节奏与层次。
- [Zajno Motion](https://motion.zajno.com/)：快起慢停的缓动、小幅位移，以及同屏元素的节奏。
- [Seesaw](https://www.seesaw.website/)、[Recent](https://recent.design/)、[Inspora](https://www.inspora.design/)：信息分组、留白和卡片内容层次，用于整理总览数字与说明。
- [Viewport UI](https://viewport-ui.design/)：局部交互反馈；[Motion](https://www.motionin.design/)：交互连续性与减少动态效果的处理。其大型画廊和持续场景动画不适用于当前数据看板。
- [posts.design](https://posts.design/)：公告类视觉的标题层次，仅作为排版参考。
- [Mobbin animations](https://mobbin.com/discover/apps/ios/animations)：本次未登录只能查看公开介绍页，未将受限动画内容作为实现依据。

## 验证

在 `frontend` 运行 `npm test` 和 `npm run build`。DOM 回归覆盖动态 class 更新后的导航层级、快速切换、横向滚动、减少动态效果、弹窗关闭与卸载清理。现有详情测试继续验证按需挂载、关闭和账号切换。

浏览器使用模拟快照检查桌面及手机布局、日夜主题、原生模态状态、Escape、焦点恢复和横向溢出；它验证界面行为，不依赖私人游戏账号。
