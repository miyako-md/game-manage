"""LoL 数据端点。LCU 路径校准来源：C:\\GPT\\LOLhelper pigeon/lcu.py 与 collector.py。"""
SUMMONER_CURRENT = "/lol-summoner/v1/current-summoner"   # LOLhelper 已验证
GAMEFLOW_PHASE = "/lol-gameflow/v1/gameflow-phase"       # LOLhelper 已验证
RANKED_STATS = "/lol-ranked/v1/ranked-stats/{puuid}"     # 未验证（Task 10 时客户端未运行，待人工校准，见 README）
MATCH_HISTORY = ("/lol-match-history/v1/products/lol/{puuid}"
                 "/matches?count={count}&startIndex=0")  # LOLhelper 已验证
GAME_DETAIL = "/lol-match-history/v1/games/{game_id}"    # LOLhelper collector 已验证

# ---- 官网新闻/公告（Task 7 Step 5 在线校准 2026-09-13，实测证据见 test_lol_news.py）----
# news/index.shtml 为 JS 动态渲染的 GBK 页面，HTML 内无新闻数据；真实数据源是页面引用的
# /v3/js/newslist.js 中的腾讯 CMC 内容接口（实测 200）。不带 r0=jsonp 时返回明文 JSON；
# 带 r0=jsonp 则 JSONP 包裹 callback(...)（回调参数名 r1）。同一端点以 target 参数区分
# 分类（即 news/index.shtml 各 tab 的 data-newsId）：
#   23=综合(NEWS 能力) 24=公告(ANNOUNCEMENT 能力) 25=赛事 27=攻略 28=社区
# 条目真实字段：sTitle / sIdxTime("YYYY-MM-DD HH:MM:SS") / sRedirectURL(可为空串) /
# iDocID / sVID / sDesc / sTagIds；sRedirectURL 为空时官方前端回退拼
# https://lol.qq.com/news/detail.shtml?docid={iDocID}（视频条目走 v/v2/detail.shtml）。
NEWS_PAGE = "https://lol.qq.com/news/index.shtml"
NEWS_LIST_URL = ("https://apps.game.qq.com/cmc/zmMcnTargetContentList"
                 "?page={page}&num={num}&target={target}&source=web_pc")  # 校准：实测 200
NEWS_CROSS_URL = ("https://apps.game.qq.com/cmc/cross/toc"
                  "?serviceId=3&source=zm&tagids={tagids}&typeids=1,2&withtop=yes"
                  "&start={start}&limit={limit}")  # newslist.js TypeCross 备用接口，实测 200
NEWS_CATEGORY_IDS = {"综合": "23", "公告": "24", "赛事": "25", "攻略": "27", "社区": "28"}
NEWS_JSON_CANDIDATES = [
    "https://lol.qq.com/act/lbcp/json/news_list.json",  # 校准结论：404，已废弃
]
