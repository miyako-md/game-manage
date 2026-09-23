"""LoL 数据端点。"""
SUMMONER_CURRENT = "/lol-summoner/v1/current-summoner"   # 已用真实客户端验证
RANKED_STATS = "/lol-ranked/v1/ranked-stats/{puuid}"     # 未用真实客户端验证
# 国服 LCU 拒绝 count/startIndex 查询参数（"Unknown argument 'count'"，
# 2026-09-13 实测）；不带任何 query 参数返回 200 + 默认最近 20 场
MATCH_HISTORY = "/lol-match-history/v1/products/lol/{puuid}/matches"
GAME_DETAIL = "/lol-match-history/v1/games/{game_id}"    # 已用真实客户端验证

# 官网新闻/公告（2026-09-13 在线校准，实测样本见 test_lol_news.py）
# news/index.shtml 为 JS 动态渲染的 GBK 页面，HTML 内无新闻数据；真实数据源是页面引用的
# /v3/js/newslist.js 中的腾讯 CMC 内容接口（实测 200）。不带 r0=jsonp 时返回明文 JSON；
# 带 r0=jsonp 则 JSONP 包裹 callback(...)（回调参数名 r1）。同一端点以 target 参数区分
# 分类（即 news/index.shtml 各 tab 的 data-newsId）：
#   23=综合(NEWS 能力) 24=公告(ANNOUNCEMENT 能力) 25=赛事 27=攻略 28=社区
# 条目真实字段：sTitle / sIdxTime("YYYY-MM-DD HH:MM:SS") / sRedirectURL(可为空串) /
# iDocID / sVID / sDesc / sTagIds；sRedirectURL 为空时官方前端回退拼
# https://lol.qq.com/news/detail.shtml?docid={iDocID}（视频条目走 v/v2/detail.shtml）。
NEWS_LIST_URL = ("https://apps.game.qq.com/cmc/zmMcnTargetContentList"
                 "?page={page}&num={num}&target={target}&source=web_pc")  # 校准：实测 200
NEWS_CATEGORY_IDS = {"综合": "23", "公告": "24", "赛事": "25", "攻略": "27", "社区": "28"}
