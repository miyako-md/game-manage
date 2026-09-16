# Wuwa expansion contracts (schema version 1)

This document defines the Task 1 backend interface. Existing snapshot HTTP envelopes and original account/role summary fields remain unchanged. New capabilities are `combat`, `activities`, `resources`. Every new capability payload carries account `role_id`, `server_id`, `schema_version: 1`, and `provenance: {source,endpoint,fetched_at}`. `source` is `https://api.kurobbs.com`; times are ISO 8601 UTC. Never interpret null/missing as zero. Upstream nested fields are preserved recursively in snake_case, including fields added by the service. Numeric/string source values retain their types. URL/image fields admit only absolute HTTP(S).

## Account and character identity

`account` keeps `{nickname,level,extra}`. `extra.role_id` and `extra.server_id` identify the account, while `extra.profile` is normalized `baseData`, including:

```json
{"creat_time":1780000000000,"world_level":8,"active_days":100,"achievement_count":200,"achievement_star":1000,"big_count":20,"small_count":100,"box_list":[{"box_name":"简易奇藏箱","id":1,"num":0}],"treasure_box_list":[{"id":1,"name":"声匣","num":null}],"phantom_box_list":[{"id":1,"name":"收集项","num":2}]}
```

These are illustrative values, never seeded data. `creat_time` preserves the upstream typo and milliseconds. All actual baseData fields are retained (energy, liveness, weekly, rouge, etc.). Token-only legacy accounts still have the original summary without profile.

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

Periods retain upstream ordering; first month is default. Reports are **resources acquired within the period**, never balances. `item_list` preserves all actual resource types; `coin_list/star_list` rows keep `type,num,sort`. An unavailable report leaves periods usable and an explicit `error`; an earlier report may be returned as `current.state=stale`, with its own unchanged period/time. `current=null` means unavailable/no month. Empty or malformed period data must not authorize a report request.

## On-demand private routes

`GET /api/wuwa/roles/{character_id}` (route placeholder named role_id in OpenAPI) validates decimal ID and checks current roleData ownership before requesting getRoleDetail.

```json
{"payload":{"schema_version":1,"role_id":"ACCOUNT","server_id":"SERVER","character_id":"1501","provenance":{"source":"https://api.kurobbs.com","endpoint":"getRoleDetail","fetched_at":"2026-09-16T04:00:00+00:00"},"data":{"role":{"role_id":1501,"role_name":"角色","level":80},"level":80,"active_branch_id":0,"role_attribute_list":[{"attribute_id":1,"attribute_name":"生命","attribute_value":"10000","sort":1,"icon_url":null}],"skill_list":[{"level":1,"active_branch":false,"skill":{"id":1,"name":"技能","description":"文本","type":"普通攻击","icon_url":null,"skill_branches":[]}}],"chain_list":[{"order":1,"name":"共鸣链","description":"文本","unlocked":false,"icon_url":null}],"weapon_data":{"level":80,"breach":6,"reson_level":1,"weapon":{"weapon_id":1,"weapon_name":"实际装备武器","weapon_star_level":5,"weapon_type":1,"weapon_effect_name":"效果","effect_description":"文本","weapon_icon":null},"main_prop_list":[]},"phantom_data":{"cost":12,"equip_phantom_list":[]},"equip_phantom_attribute_list":[],"equip_phantom_add_prop_list":[],"role_skin":null}},"fetched_at":"2026-09-16T04:00:00+00:00"}
```

Each `equip_phantom_list` entry preserves `cost,quality,level,main_props,phantom_prop,fetter_detail` plus any additional actual fields. Show missing substats as unavailable, never generate them. Descriptions are untrusted text (no raw HTML injection).

`GET /api/wuwa/resources/{kind}/{period}` permits week/month/version and periods returned by a **fresh** period/list read for current credentials. Success envelope is `{payload:{schema_version,role_id,server_id,kind,period,data,provenance},fetched_at}`; `data` is the same normalized report shape above.

Both routes share LoginService lock/renewal and check generation before publication. Responses: 401 unconfigured/expired, 404 unknown owned character/period or disabled game, 409 changed session (retry), 422 malformed path, 502 upstream/parse failure. No route accepts arbitrary upstream URLs. Same-account ticket renewal is accepted when the result credential version is current; the separate `LoginService.account_generation(game)` epoch changes on login/logout, so actual session switches are rejected. Route success can be hooked for Task 2 role_detail archive, using payload account identity and a current session check. No history/gacha endpoints are added by Task 1.

