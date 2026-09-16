# Wuwa expansion contracts (schema version 1)

This document defines the Task 1 backend interface. Existing snapshot HTTP envelopes and original account/role summary fields remain unchanged. New capabilities are `combat`, `activities`, `resources`. Every new capability payload carries account `role_id`, `server_id`, `schema_version: 1`, and `provenance: {source,endpoint,fetched_at}`. `source` is `https://api.kurobbs.com`; times are ISO 8601 UTC. Never interpret null/missing as zero. Upstream nested fields are preserved recursively in snake_case, including fields added by the service. Numeric/string source values retain their types. URL/image fields admit only absolute HTTP(S).

## Account and character identity

`account` keeps `{nickname,level,extra}`. `extra.role_id` and `extra.server_id` identify the account, while `extra.profile` is normalized `baseData`, including:

```json
{"creat_time":1780000000000,"world_level":8,"active_days":100,"achievement_count":200,"achievement_star":1000,"big_count":20,"small_count":100,"box_list":[{"box_name":"简易奇藏箱","id":1,"num":0}],"treasure_box_list":[{"id":1,"name":"朴素奇藏箱","num":null}],"phantom_box_list":[{"id":1,"name":"潮汐之遗·绿","num":2}]}
```

These are illustrative values, never seeded data. `creat_time` preserves the upstream typo and milliseconds. Live collection labels were rechecked: box_list and treasure_box_list both list 奇藏箱 tiers (do not sum overlapping counts); phantom_box_list lists 潮汐之遗 colors, not equipped echoes or a sonance-casket count. All actual baseData fields are retained (energy, liveness, weekly, rouge, etc.). Token-only legacy accounts still have the original summary without profile.

`roles` remains an array of original `RoleEntry` objects: `{role_id,name,level,attribute,breach,chain,star_level,weapon,icon_url,is_main,extra}`. Its outer `role_id` is the **character ID**, and `weapon` is the **weapon type**, never an equipped weapon. `extra` contains all normalized roleData entry fields (`total_skill_level`, `role_skin`, `attribute_id`, `weapon_type_id`, `role_pic_url`, etc.) plus `account_role_id`, `server_id`, and `provenance` for archive isolation. `extra.role_id` also remains the upstream character ID. A role detail response carries account `role_id` and separate `character_id`.

## Combat

```json
{"schema_version":1,"role_id":"ACCOUNT","server_id":"SERVER","provenance":{"source":"https://api.kurobbs.com","endpoint":"combat","fetched_at":"2026-09-16T04:00:00+00:00"},"tower":{"state":"ok","source":"towerDataDetail","fetched_at":"2026-09-16T04:00:00+00:00","error":null,"data":{"is_unlock":true,"season_end_time":60000,"season_end_at":"2026-09-16T04:01:00+00:00","difficulty_list":[{"difficulty":3,"difficulty_name":"深境区","tower_area_list":[{"area_id":1,"area_name":"示例区域","star":0,"max_star":12,"floor_list":[{"floor":1,"star":0,"max_star":3,"role_list":[{"role_id":1501}]}]}]}]}},"hologram":{"state":"error","source":"challengeDetails","fetched_at":null,"error":"来源请求失败，请稍后重试","data":null},"slash":{"state":"ok","source":"slashDetail","fetched_at":"2026-09-16T04:00:00+00:00","error":null,"data":{"is_unlock":false}}}
```

Each subsource has `{state:ok|stale|error,data,fetched_at,source,error}`. Partial failure keeps successful siblings; stale retains that subsource's previous successful data/time. Display stale errors and timestamps explicitly. Tower `season_end_time` is **remaining milliseconds at fetch**, `season_end_at` is derived absolute time. Expired/missing durations are rejected, never published as current results. Keep every difficulty in archive; UI defaults to `difficulty == 3`. Area/floor/team field names come directly from normalized source; do not invent missing teams/stars.

Live 2026-09-16 structures: hologram `data.challenge_info` is an object keyed by challenge group ID; each value is an array with `challenge_id,boss_name,boss_level,difficulty,pass_time,boss_head_icon,boss_icon_url` and optional `roles` (`role_name,role_head_icon,role_level`). Slash has `difficulty_list[].{difficulty,difficulty_name,all_score,max_score,challenge_list,home_page_bg,detail_page_bg,team_icon}`; `challenge_list[]` contains `challenge_id,challenge_name,score,rank,half_list`; each half keeps `role_list`, buffs, score.

## Activities

```json
{"schema_version":1,"role_id":"ACCOUNT","server_id":"SERVER","provenance":{"source":"https://api.kurobbs.com","endpoint":"moreActivity","fetched_at":"2026-09-16T04:00:00+00:00"},"sections":{"permanent_rouge":{"title":"浸梦海床","score":0,"max_score":100,"sort":1},"trap_defense":{"title":"玩法","sort":2,"high":{"count":0,"total":10},"low":{"count":null,"total":10}}}}
```

All actual returned sections are retained, including new ones. Live sections also include `floro_ranch` (animal/map/toy count, reward), `honami_story` (items, item_num, max_item_num, level), `phantom_battle` (badge/card/level/exp), `phantom_battle_record` (card/level/exp). Render their title/sort and actual fields rather than limiting UI to the older reference's two sections. Entire source errors use normal snapshot failure retention.

## Resources

```json
{"schema_version":1,"role_id":"ACCOUNT","server_id":"SERVER","provenance":{"source":"https://api.kurobbs.com","endpoint":"resource","fetched_at":"2026-09-16T04:00:00+00:00"},"periods":{"week":[{"period":"1","title":"本周"}],"month":[{"period":"1","title":"本月"}],"version":[]},"current":{"kind":"month","period":"1","state":"ok","fetched_at":"2026-09-16T04:00:00+00:00","data":{"total_coin":0,"total_star":null,"coin_list":[],"star_list":[],"item_list":[{"type":1,"total":0,"inc":"0%","detail":[]}],"coin_inc":"0%","star_inc":"0%","copy_writing":"来源文案","recommend":null}},"error":null}
```

Periods retain upstream ordering for selection buttons. The default is the greatest valid YYYYMM period (four-digit nonzero year, month 01–12), independent of list order and across year boundaries. Unknown formats are excluded from date comparison; if none are valid YYYYMM, the first source period is the compatibility fallback, without claiming it is chronologically latest. Titles are never parsed as dates. Reports are **resources acquired within the period**, never balances. `item_list` preserves all actual resource types; `coin_list/star_list` rows keep `type,num,sort`. An unavailable report leaves periods usable and an explicit `error`; an earlier report may be returned as `current.state=stale`, with its own unchanged period/time. `current=null` means unavailable/no month. Empty or malformed period data must not authorize a report request.

## On-demand private routes

`GET /api/wuwa/roles/{character_id}` (route placeholder named role_id in OpenAPI) validates decimal ID and checks current roleData ownership before requesting getRoleDetail.

```json
{"payload":{"schema_version":1,"role_id":"ACCOUNT","server_id":"SERVER","character_id":"1501","provenance":{"source":"https://api.kurobbs.com","endpoint":"getRoleDetail","fetched_at":"2026-09-16T04:00:00+00:00"},"data":{"role":{"role_id":1501,"role_name":"角色","level":80},"level":80,"active_branch_id":0,"role_attribute_list":[{"attribute_id":1,"attribute_name":"生命","attribute_value":"10000","sort":1,"icon_url":null}],"skill_list":[{"level":1,"active_branch":false,"skill":{"id":1,"name":"技能","description":"文本","type":"普通攻击","icon_url":null,"skill_branches":[]}}],"chain_list":[{"order":1,"name":"共鸣链","description":"文本","unlocked":false,"icon_url":null}],"weapon_data":{"level":80,"breach":6,"reson_level":1,"weapon":{"weapon_id":1,"weapon_name":"实际装备武器","weapon_star_level":5,"weapon_type":1,"weapon_effect_name":"效果","effect_description":"文本","weapon_icon":null},"main_prop_list":[]},"phantom_data":{"cost":12,"equip_phantom_list":[]},"equip_phantom_attribute_list":[],"equip_phantom_add_prop_list":[],"role_skin":null}},"fetched_at":"2026-09-16T04:00:00+00:00"}
```

Each `equip_phantom_list` entry preserves `cost,quality,level,main_props,phantom_prop,fetter_detail` plus any additional actual fields. Show missing substats as unavailable, never generate them. Descriptions are untrusted text (no raw HTML injection).

`GET /api/wuwa/resources/{kind}/{period}` permits week/month/version and periods returned by a **fresh** period/list read for current credentials. Success envelope is `{payload:{schema_version,role_id,server_id,kind,period,data,provenance},fetched_at}`; `data` is the same normalized report shape above.

Both routes share LoginService lock/renewal and check generation before publication. Responses: 401 unconfigured/expired, 404 unknown owned character/period or disabled game, 409 changed session (retry), 422 malformed path, 502 upstream/parse failure. No route accepts arbitrary upstream URLs. Same-account ticket renewal is accepted when the result credential version is current; the separate `LoginService.account_generation(game)` epoch changes on login/logout, so actual session switches are rejected. Route success can be hooked for Task 2 role_detail archive, using payload account identity and a current session check. No history/gacha endpoints are added by Task 1.

## Task 2: local history and explicit gacha import

All four archive endpoints use the active adapter's account role ID and server ID. They require configured credentials and both IDs (401 otherwise); logout hides all archived data without destroying it. Account switches do not mix records. Responses set `Cache-Control: no-store`, `Pragma: no-cache`, `Referrer-Policy: no-referrer`.

Both POST routes require `X-Game-Assistant: 1`, an allowed configured local Host, and, when Origin is present, an exact match to the request's scheme/host/port. Body size is checked from both Content-Length and actual streamed bytes (2 MiB maximum). Malformed bodies and import errors return generic/non-reflective 422 details, never the submitted link. These POST bodies are parsed explicitly rather than echoed in validation errors.

### History

`GET /api/wuwa/history?kind=tower|roles|role_detail&limit=100&offset=0` returns this exact empty shape (identity values illustrative):

```json
{"schema_version":1,"role_id":"ACCOUNT","server_id":"SERVER","kind":"tower","items":[],"total":0,"limit":100,"offset":0,"archive_started_at":null,"complete":false,"coverage":"仅保存成功观测；首条记录之前的成绩和练度未知"}
```

`limit` is 1–500 and `offset` 0–1000000. Items are newest archive insertion first. Tower archive item example:

```json
{"id":1,"subject":"","season":"2026-09-30T12:00:00+00:00","payload":{"season_end_at":"2026-09-30T12:00:00.100+00:00","season_end_time":10000,"difficulty_list":[{"star":0}]},"source":"towerDataDetail","source_at":"2026-09-16T04:00:00+00:00","observed_at":"2026-09-16T04:00:01+00:00","archived_at":"2026-09-16T04:00:01+00:00","delta":null}
```

`source_at` is the upstream payload's collection time; `observed_at` is local observation time (the original snapshot time for backfill); `archived_at` is actual local insertion time. `archive_started_at` is the earliest insertion for this account/server/kind. No version label is invented. `season` rounds the absolute season end to the nearest minute so millisecond drift does not create false seasons; original precise end remains in payload. Data expired **at its source collection time** is rejected, while valid older-season snapshots can be backfilled. All tower difficulties are preserved. Stale/error towers are never archived.

Successful scheduler snapshot saves automatically archive role-list training observations, one item per character (`subject` is character ID). Full details are archived only after a successful user-requested role-detail read and session validation (`kind=role_detail`). Timestamp/provenance-only changes are ignored; repeated content within account/server/kind/character/season is deduplicated against its latest observation, while a real change and later reversion both remain. First observations have `delta:null`; later observations compare only the same character/season. Example changed fields: `{"level":{"before":null,"after":0,"delta":null}}` then `{"level":{"before":0,"after":1,"delta":1}}`. Arrays are compared as complete changed values. Unknown values are never subtracted as zero.

`POST /api/wuwa/history/backfill` accepts `{}`. It reads at most the existing local `combat` and `roles` snapshots, validates embedded identity, and never requests gacha or invents earlier scores. Exact empty outcome:

```json
{"inserted":0,"complete":false,"sources":["local_snapshot"],"message":"仅回补现存同账号快照；官方无已验证的历史成绩接口，未推测旧记录"}
```

### Gacha

`GET /api/wuwa/gacha?limit=100&offset=0` is local-only; neither page loads, normal refresh, scheduler nor history backfill collect gacha. The only collection trigger is the explicit `POST /api/wuwa/gacha/import`. No real user link was requested or used during implementation validation.

Import chooses exactly one body field:

```json
{"url":"https://gmserver-api.aki-game2.com/gacha/record/query?record_id=TRANSIENT&player_id=ACCOUNT&server_id=SERVER"}
```

```json
{"records":{"info":{"uid":"ACCOUNT","export_app":"WWUID"},"list":[{"cardPoolType":"1","resourceId":1501,"qualityLevel":5,"resourceType":"角色","name":"示例角色","count":1,"time":"2026-09-01 12:00:00"}]}}
```

Normalized JSON can instead use `{"records":{"role_id":"ACCOUNT","server_id":"SERVER","records":[{"pool":"1","resource_id":"1501","rarity":5,"resource_type":"角色","name":"示例角色","count":1,"time":"2026-09-01T12:00:00"}]}}`. A bare records array must include matching `role_id`/`uid`/`playerId`/`player_id`/`account_role_id` in **every** row. Missing ownership fails with `每批抽卡记录必须包含匹配的账号标识`; mismatching IDs or supplied servers are rejected. A standard WWUID export without server is assigned to the active server only after UID matches; this is imported-file attribution, not independent verification of the file's authenticity.

Link parsing supports query and `#/record?...` fragment, snake/camel aliases `record_id|recordId`, `player_id|playerId`, `server_id|serverId|svr_id`. Conflicting/duplicate aliases, non-HTTPS links, userinfo, nonstandard ports, unknown hosts and mismatched player/server fail closed. Recognized link hosts are exact `gmserver-api.aki-game2.com/.net` and `aki-gm-resources.aki-game.com/.net`. The provided URL is never fetched: requests go only to the fixed regional `https://gmserver-api.aki-game2.com|net/gacha/record/query`, with redirects and environment proxies disabled. The active account server determines region. Record authorization stays in memory only; raw links, recordId, source unknown fields and upstream exception/response texts are not persisted or returned.

Official import requests pools 1–9 once each; a malformed/failed/redirected pool is listed in `failed_pools`, while successful pools remain importable. Each response is limited to 8 MiB, with 15-second HTTP timeout, and the combined import to 20000 rows. JSON also caps at 20000 rows. Unknown additional pools and rarity values in JSON are retained. `rarity:null` becomes `unknown` only in aggregate display; rows keep null. Count is retained as source item quantity; pull totals count rows, never quantity stacks. Time strings preserve the source timezone convention, normalizing only ISO formatting.

Dedup uses explicit `draw_id`/`id` when supplied; otherwise it uses a hash of normalized draw fields plus within-batch occurrence ordinal. Thus two identical same-second items remain two draws, and repeat imports remain idempotent. Without source IDs, nonoverlapping fragments containing indistinguishable same-second items cannot be proven distinct; the archive conservatively retains the maximum observed multiplicity, not an invented sum.

Exact one-row import outcome (values vary with actual input):

```json
{"inserted":1,"received":1,"failed_pools":[],"complete":false,"state":"imported"}
```

`state` is `partial` when any official pool fails, `need_import` on an empty successful import, otherwise `imported`. All failures remain an explicit partial result and do not erase old draws. The account generation is checked again after network requests; a login/logout/switch returns 409 and discards all in-flight rows. Same-account ticket renewal is allowed.

Exact never-imported GET shape:

```json
{"schema_version":1,"role_id":"ACCOUNT","server_id":"SERVER","state":"need_import","total":0,"items":[],"gold":[],"gold_total":0,"pools":[],"limit":100,"offset":0,"coverage":{"earliest":null,"latest":null,"complete":false,"imported_at":null,"source":null,"failed_pools":[],"message":"仅代表已导入记录；官方保留期及导出范围可能不完整，无保底推断"}}
```

With data, state is `available`, `items` are bounded normalized draws including `draw_id,pool,resource_id,rarity,resource_type,name,count,time`, and `gold` contains rarity `"5"` draws with its own `gold_total`. Both lists use the requested limit/offset independently; full-archive counts are not limited to the page. Pools have e.g. `{"pool":"1","name":"角色精准调谐","total":2,"rarity_distribution":{"5":1,"unknown":1}}`; unknown pool 99 is `未知卡池 99`. Coverage includes earliest/latest imported draw times and latest import time/source (`json_import|official_query`), always `complete:false`. A successful fetch is never proof of full account history; no pity/guarantee counter is computed.
