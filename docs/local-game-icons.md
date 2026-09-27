# 本机游戏图标

公开仓库默认使用原创文字标识。本机可把自备图片放到 `frontend/public/local-game-icons/`，文件名使用游戏 ID：

- `wuthering_waves.jpg`
- `nte.jpg`
- `league_of_legends.svg`

每款游戏支持 png、jpg、webp、svg，按此顺序选择。运行 `npm run build --prefix frontend` 后刷新页面；开发模式需要重启 Vite。构建时仅为实际存在的图片生成映射，不会为未安装图标请求不存在的地址。加载失败会自动回退到公开版标识。

该目录已被 Git 忽略，本机图片不会跟随源码提交。构建产物会包含本机图片；如需分发构建包，请在不含此目录的干净检出中构建。
