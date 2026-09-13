"""LoL 数据端点。LCU 路径校准来源：C:\\GPT\\LOLhelper pigeon/lcu.py 与 collector.py。"""
SUMMONER_CURRENT = "/lol-summoner/v1/current-summoner"   # LOLhelper 已验证
GAMEFLOW_PHASE = "/lol-gameflow/v1/gameflow-phase"       # LOLhelper 已验证
RANKED_STATS = "/lol-ranked/v1/ranked-stats/{puuid}"     # 未验证，Task 10 校准
MATCH_HISTORY = ("/lol-match-history/v1/products/lol/{puuid}"
                 "/matches?count={count}&startIndex=0")  # LOLhelper 已验证
GAME_DETAIL = "/lol-match-history/v1/games/{game_id}"    # LOLhelper collector 已验证
