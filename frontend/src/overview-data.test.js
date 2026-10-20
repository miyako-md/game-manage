import test from 'node:test'
import assert from 'node:assert/strict'
import { dailyTasks, deadlineDays, gachaDigests, resetLabel } from './overview-data.js'

const now = Date.parse('2026-10-17T12:00:00+08:00')
const wuwa = { game_id: 'wuthering_waves', display_name: '鸣潮' }
const nte = { game_id: 'nte', display_name: '异环' }
const endfield = { game_id: 'endfield', display_name: '终末地', credentials_configured: true }

test('reset times read as today, tomorrow, a weekday, or days away, in Beijing time', () => {
  assert.equal(resetLabel(Date.parse('2026-10-17T20:00:00+08:00'), now), '今天 20:00 重置')
  assert.equal(resetLabel(Date.parse('2026-10-18T04:00:00+08:00'), now), '明天 04:00 重置')
  assert.equal(resetLabel(Date.parse('2026-10-19T04:00:00+08:00'), now), '周一 04:00 重置')
  assert.equal(resetLabel(Date.parse('2026-10-30T04:00:00+08:00'), now), '13 天后重置')
  assert.equal(resetLabel(Date.parse('2026-10-16T04:00:00+08:00'), now), '')
})

test('daily tasks: the daily items lead, weekly ones follow by reset, stale or goal-less items stay out', () => {
  const snapshots = {
    wuthering_waves: { progress: { payload: [
      { name: '逆境深塔·深境区', cur: 28, total: 36, refresh_at: '2026-10-03T04:00:00+08:00' },
      { name: '战歌重奏收取次数', cur: 2, total: 3, refresh_at: '2026-10-19T04:00:00+08:00' },
      { name: '终焉矩阵', cur: 0, total: 0, refresh_at: null },
      { name: '活跃度', cur: 100, total: 100, refresh_at: '2026-10-18T04:00:00+08:00' },
      { name: '结晶单质', cur: 350, total: 480, refresh_at: null },
      { name: '版本赏令', cur: 42, total: 70, refresh_at: '2026-11-12T03:59:00+08:00' },
    ] } },
    nte: { stamina: { payload: { schema_version: 1, daily_activity: 70, weekly_remaining: 0 } } },
    endfield: { progress: { payload: { schema_version: 1, items: [{ id: 'daily', name: '每日活跃', cur: 60, total: 100 }, { id: 'battle_pass', name: '通行证', cur: 3, total: 60 }] } } },
  }
  const tasks = dailyTasks([wuwa, nte, endfield], snapshots, now)
  assert.deepEqual(tasks.map(task => [task.name, task.done, task.reset]), [
    ['活跃度', true, '明天 04:00 重置'], ['日常活跃', false, ''], ['每日活跃', false, ''],
    ['战歌重奏收取次数', false, '周一 04:00 重置'], ['周本剩余', true, ''],
  ])
  // An unversioned NTE payload is never misread.
  assert.deepEqual(dailyTasks([nte], { nte: { stamina: { payload: { daily_activity: 70 } } } }, now), [])
})

test('deadline days count per Beijing day; a month labels every fifth day under the axis', () => {
  const events = [
    { gameName: '鸣潮', endTime: Date.parse('2026-10-17T23:59:00+08:00') },
    { gameName: '异环', endTime: Date.parse('2026-10-17T23:00:00+08:00') },
    { gameName: '鸣潮', endTime: Date.parse('2026-10-18T03:59:00+08:00') },
    { gameName: '鸣潮', endTime: Date.parse('2026-11-10T03:59:00+08:00') },
  ]
  const week = deadlineDays(events, now, 7)
  assert.deepEqual(week.slice(0, 3).map(day => [day.label, day.value, day.note]), [['今天', 2, '鸣潮 1 · 异环 1'], ['明天', 1, '鸣潮 1'], ['周一', 0, '']])
  const month = deadlineDays(events, now, 30)
  assert.equal(month.length, 30)
  assert.deepEqual(month.slice(0, 6).map(day => day.tick), ['今天', '', '', '', '', '10/22'])
  assert.equal(month.reduce((sum, day) => sum + day.value, 0), 4)
})

test('gacha digests come from the Endfield ledger and the NTE community card, and only for a matching identity', () => {
  const snapshots = {
    endfield: {
      account: { payload: { schema_version: 1, role_id: 'r1' } },
      gacha: { payload: { schema_version: 1, role_id: 'r1', report: { schema_version: 1, role_id: 'r1', total: 286, six_star: 5, known_exact_intervals: 1, average_exact_pulls: 66.4 },
        pools: [{ key: 'E_CharacterGachaPoolType_Special', label: '特许寻访', since_last_six: { count: 20, status: 'lower_bound' },
          history: [{ name: '提弗洛斯', pool_name: '冬猎', obtained_at: 1791387394087, pulls: 66, status: 'exact' }] }] } },
    },
    nte: { gacha: { payload: { schema_version: 1, total_draws: 638, total_s: 9, luck_title: '欧气冲天', pools: [
      { name: '限定角色棋盘', details: [{ name: '夜航', pity: 88, obtained_at: '2026-09-05T12:02:00+08:00' }, { name: '星穹旅人', pity: 34, obtained_at: '2026-09-20T21:14:00+08:00' }] },
    ] } } },
  }
  const [first, second] = gachaDigests([endfield, nte], snapshots)
  assert.deepEqual([first.total, first.stats.map(stat => stat.value), first.latest.detail], [286, [5, '66 抽', '≥20 抽'], '冬猎 · 66 抽'])
  assert.deepEqual([second.total, second.stats.map(stat => stat.value), second.latest.name], [638, [9, '61 抽', '欧气冲天'], '星穹旅人'])
  const other = { ...snapshots, endfield: { ...snapshots.endfield, account: { payload: { schema_version: 1, role_id: 'someone-else' } } } }
  assert.deepEqual(gachaDigests([endfield], other).length, 0)
})

test('a merged overview uses the passport identity even when the displayed account comes from Skland', () => {
  const snaps = { account: { payload: { schema_version: 1, nickname: '森空岛角色' } },
    passport_account: { payload: { role_id: 'r1' } },
    gacha: { payload: { role_id: 'r1', report: { schema_version: 1, role_id: 'r1', total: 12 } } } }
  assert.equal(gachaDigests([endfield], { endfield: snaps })[0].total, 12)
  for (const passport_account of [null, { payload: { role_id: 'other' } }, { state: 'auth_expired', payload: { role_id: 'r1' } }]) {
    assert.deepEqual(gachaDigests([endfield], { endfield: { ...snaps, passport_account } }), [])
  }
})

test('the Endfield pull card counts operator headhunting only once the ledger also holds weapon requisition', () => {
  const pool = (key, kind, total, six, history) => ({ key, label: key, kind, total, six_star: six, history })
  const snaps = { account: { payload: { schema_version: 1, role_id: 'r1' } },
    gacha: { payload: { schema_version: 1, role_id: 'r1', report: { schema_version: 1, role_id: 'r1', total: 230, six_star: 6, known_exact_intervals: 3, average_exact_pulls: 30 },
      pools: [pool('E_CharacterGachaPoolType_Special', 'character', 150, 2, [{ name: '伊冯', pulls: 70, status: 'exact', obtained_at: 2 }]),
        pool('weapon:w1', 'weapon', 80, 4, [{ name: '遥望', pulls: 10, status: 'exact', obtained_at: 9 }, { name: '玉中身', pulls: 10, status: 'exact', obtained_at: 8 }])] } } }
  const [digest] = gachaDigests([endfield], { endfield: snaps })
  assert.deepEqual([digest.total, digest.scope, digest.stats[0].value, digest.stats[1].value, digest.latest.name], [150, '干员寻访', 2, '70 抽', '伊冯'])
})


test('daily completion retains historical values but requires evidence of the current cycle', () => {
  const now = Date.parse('2026-10-20T12:00:00+08:00')
  const progress = (extra, refresh_at) => ({ wuthering_waves: { progress: {
    fetched_at: '2026-10-19T23:00:00+08:00', ...extra,
    payload: [{ name: '活跃度', cur: 100, total: 100, refresh_at }],
  } } })
  const expired = dailyTasks([wuwa], progress({ stale: true, state: 'error' }, '2026-10-20T04:00:00+08:00'), now)[0]
  assert.deepEqual([expired.current, expired.total, expired.done, expired.pending], [100, 100, false, true])
  assert.equal(dailyTasks([wuwa], progress({ stale: false, state: 'ok' }, '2026-10-20T04:00:00+08:00'), now)[0].done, false)
  const current = dailyTasks([wuwa], progress({ stale: true, state: 'error', fetched_at: '2026-10-20T10:00:00+08:00' }, '2026-10-21T04:00:00+08:00'), now)[0]
  assert.deepEqual([current.done, current.pending, current.retained], [true, false, true])
  assert.equal(dailyTasks([wuwa], progress({ stale: true }, null), now)[0].pending, true)
  assert.equal(dailyTasks([wuwa], progress({ stale: false, state: 'ok' }, null), now)[0].done, true)
  const nteTasks = dailyTasks([nte], { nte: { stamina: { stale: true, payload: { schema_version: 1, daily_activity: 100, weekly_remaining: 0 } } } }, now)
  assert.deepEqual(nteTasks.map(task => [task.current, task.done, task.pending]), [[100, false, true], [0, false, true]])
})
