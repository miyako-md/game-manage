import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick, reactive } from 'vue'
import { loadVue, mount, content, nodes } from '../test-utils/vue.js'

const component = (name) => loadVue(new URL(`./${name}.vue`, import.meta.url))
const tick = async () => {
  await new Promise((resolve) => setImmediate(resolve))
  await nextTick()
}
const click = async (root, label) => {
  const button = nodes(root, 'button').find((n) => content(n).includes(label))
  assert.ok(button, label)
  button.props.onClick({ preventDefault() {} })
  await tick()
}
const identity = { role_id: 'account', server_id: 'server' }
const snap = (payload) => ({
  payload,
  fetched_at: '2026-09-16T04:00:00Z',
  stale: false,
})
const account = snap({
  nickname: '漂泊者',
  level: 0,
  extra: {
    ...identity,
    profile: {
      world_level: null,
      active_days: 0,
      achievement_count: 0,
      box_list: [{ box_name: '简易奇藏箱', num: 0 }],
    },
  },
})
const reply = (payload) => ({ ok: true, json: async () => payload })

test('whole snapshot staleness remains visible when nested source states were once ok', async (t) => {
  const root = mount(t, await component('WuwaCombat'), {
    snap: {
      ...snap({ tower: { state: 'ok', data: { difficulty_list: [] } } }),
      stale: true,
    },
  })
  assert.match(content(root), /旧数据/)
})

test('profile preserves zero, unknown world level and independent collection counts', async (t) => {
  const root = mount(t, await component('WuwaProfile'), { snap: account })
  assert.match(content(root), /世界等级 未知/)
  assert.match(content(root), /活跃天数 0/)
  assert.match(content(root), /简易奇藏箱 0/)
})
test('role detail uses actual weapon and nested echo set, never copies aggregate substats', async (t) => {
  const root = mount(t, await component('WuwaRoleDetail'), {
    data: {
      role: { role_name: '今汐' },
      role_attribute_list: [
        { attribute_name: '生命', attribute_value: '10000' },
      ],
      weapon_data: {
        level: 80,
        reson_level: 1,
        weapon: { weapon_name: '时和岁稔' },
        main_prop_list: [],
      },
      phantom_data: {
        cost: 12,
        equip_phantom_list: [
          {
            level: 25,
            cost: 4,
            phantom_prop: { name: '角' },
            fetter_detail: { name: '浮星祛暗' },
            main_props: [{ attribute_name: '暴击', attribute_value: '22%' }],
          },
        ],
      },
      equip_phantom_add_prop_list: [
        { attribute_name: '暴击伤害', attribute_value: '999%' },
      ],
    },
  })
  for (const value of [
    '时和岁稔',
    '角',
    '浮星祛暗',
    '副词条 未提供',
    '生命 10000',
  ])
    assert.ok(content(root).includes(value), value)
})
test('combat defaults deep realm and preserves independent error and stale siblings', async (t) => {
  const root = mount(t, await component('WuwaCombat'), {
    snap: snap({
      tower: {
        state: 'ok',
        data: {
          difficulty_list: [
            {
              difficulty: 1,
              difficulty_name: '稳定区',
              tower_area_list: [{ area_name: '不要默认显示' }],
            },
            {
              difficulty: 3,
              difficulty_name: '深境区',
              tower_area_list: [
                {
                  area_name: '深境测试',
                  floor_list: [
                    {
                      floor: 1,
                      star: 0,
                      max_star: 3,
                      role_list: [{ role_name: '今汐' }],
                    },
                  ],
                },
              ],
            },
          ],
        },
      },
      hologram: { state: 'error', error: '来源请求失败' },
      slash: {
        state: 'stale',
        error: '稍后重试',
        fetched_at: '2026-09-15T00:00:00Z',
        data: { is_unlock: false },
      },
    }),
  })
  assert.match(content(root), /深境测试/)
  assert.doesNotMatch(content(root), /不要默认显示/)
  assert.match(content(root), /0 \/ 3/)
  assert.match(content(root), /今汐/)
  assert.match(content(root), /来源请求失败/)
  assert.match(content(root), /旧数据/)
})
test('role requests are lazy and stale responses cannot replace newer selection or switched account', async (t) => {
  const pending = []
  t.mock.method(
    globalThis,
    'fetch',
    (url, options) =>
      new Promise((resolve) => pending.push({ url, options, resolve })),
  )
  const props = reactive({
    accountKey: 'account:server',
    snap: snap([
      { role_id: '1', name: '第一位', weapon: '长刃' },
      { role_id: '2', name: '第二位', weapon: '迅刀' },
    ]),
  })
  const root = mount(t, await component('WuwaRoles'), props)
  assert.equal(pending.length, 0)
  await click(root, '第一位')
  await click(root, '第二位')
  assert.equal(pending.length, 2)
  pending[1].resolve(
    reply({
      payload: {
        ...identity,
        character_id: '2',
        data: { weapon_data: { weapon: { weapon_name: '正确武器' } } },
      },
    }),
  )
  await tick()
  pending[0].resolve(
    reply({
      payload: {
        ...identity,
        character_id: '1',
        data: { weapon_data: { weapon: { weapon_name: '过时武器' } } },
      },
    }),
  )
  await tick()
  assert.match(content(root), /正确武器/)
  assert.doesNotMatch(content(root), /过时武器/)
  props.accountKey = 'other:server'
  await tick()
  assert.doesNotMatch(content(root), /正确武器/)
})
test('resources request only selected server periods and show acquired quantity', async (t) => {
  const calls = []
  t.mock.method(globalThis, 'fetch', async (url) => {
    calls.push(url)
    return reply({
      payload: {
        ...identity,
        kind: 'week',
        period: '7',
        data: { total_coin: 0, total_star: null },
      },
    })
  })
  const root = mount(t, await component('WuwaResources'), {
    accountKey: 'account:server',
    snap: snap({
      periods: {
        week: [{ period: '7', title: '九月第二周' }],
        month: [],
        version: [],
      },
      current: null,
    }),
  })
  await click(root, '九月第二周')
  assert.equal(calls[0], '/api/wuwa/resources/week/7')
  assert.match(content(root), /期间获取/)
  assert.match(content(root), /贝币 0/)
  assert.match(content(root), /星声 未知/)
})
test('gacha loads only local archive; explicit import clears secret and displays duplicate/empty/partial outcomes', async (t) => {
  const calls = []
  let result = {
    inserted: 0,
    received: 2,
    failed_pools: ['9'],
    complete: false,
    state: 'partial',
  }
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    calls.push({ url, options })
    return reply(
      options?.method === 'POST'
        ? result
        : {
            ...identity,
            total: 0,
            items: [],
            gold: [],
            gold_total: 0,
            pools: [],
            state: 'need_import',
            coverage: { complete: false, message: '仅代表已导入记录' },
          },
    )
  })
  const root = mount(t, await component('WuwaGacha'), {
    accountKey: 'account:server',
  })
  await tick()
  assert.equal(calls.length, 1)
  assert.equal(calls[0].url, '/api/wuwa/gacha?limit=50&offset=0')
  const input = nodes(root, 'input').find((n) => n.props.type === 'password')
  input.props.onInput({
    target: { value: 'https://example.invalid/?record_id=SECRET' },
  })
  await tick()
  await click(root, '导入链接')
  assert.equal(calls[1].options.headers['X-Game-Assistant'], '1')
  assert.match(content(root), /新增 0/)
  assert.match(content(root), /收到 2/)
  assert.match(content(root), /9/)
  assert.equal(input.props.value, '')
  assert.doesNotMatch(content(root), /SECRET/)
  result = { inserted: 0, received: 0, failed_pools: [], state: 'need_import' }
  input.props.onInput({ target: { value: 'another' } })
  await click(root, '导入链接')
  assert.match(content(root), /未获得记录/)
})
test('history exposes archive origin, first observation, paged seasons and no invented backfill', async (t) => {
  const calls = []
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    calls.push(url)
    return reply(
      options?.method === 'POST'
        ? { inserted: 0, message: '仅回补现存同账号快照' }
        : {
            ...identity,
            items: [
              {
                id: 1,
                season: '2026-09-30',
                subject: '',
                observed_at: '2026-09-16',
                source_at: '2026-09-16',
                payload: { difficulty_list: [] },
                delta: null,
              },
            ],
            total: 51,
            archive_started_at: '2026-09-16',
            coverage: '首条记录之前未知',
          },
    )
  })
  const root = mount(t, await component('WuwaHistory'), {
    accountKey: 'account:server',
  })
  await tick()
  assert.match(content(root), /2026-09-16/)
  assert.match(content(root), /2026-09-30/)
  assert.match(content(root), /首次观测/)
  await click(root, '下一页')
  assert.ok(calls.includes('/api/wuwa/history?kind=tower&limit=50&offset=50'))
  await click(root, '回补')
  assert.match(content(root), /仅回补现存同账号快照/)
})
test('dashboard overview maps to profile and gacha/history remain accessible without capability flags', async (t) => {
  const root = mount(t, await component('WuwaDashboard'), {
    snaps: { account },
    initialSection: 'overview',
    configured: true,
  })
  assert.match(content(root), /漂泊者/)
  assert.ok(nodes(root, 'button').some((n) => content(n) === '抽卡历史'))
  assert.ok(nodes(root, 'button').some((n) => content(n) === '成长记录'))
})
test('nullable collections remain unknown and exploration zero is visible', async (t) => {
  const root = mount(t, await component('WuwaProfile'), {
    snap: snap({
      extra: {
        profile: {
          box_list: [null, { box_name: '朴素奇藏箱', num: 0 }],
          phantom_box_list: [{ name: '潮汐之遗·金', num: 0 }],
        },
      },
    }),
  })
  assert.match(content(root), /潮汐之遗/)
  assert.doesNotMatch(content(root), /声骸收集/)
  assert.match(content(root), /朴素奇藏箱 0/)
  const explore = mount(t, await component('ExplorationCard'), {
    snap: snap({ detections: { total: 0, by_level: {} } }),
  })
  assert.match(content(explore), /残象已收录 0/)
})
test('dynamic activity nested progress, unlock and null values render with Chinese labels', async (t) => {
  const root = mount(t, await component('WuwaActivities'), {
    snap: snap({
      sections: {
        new_version: {
          title: '新的玩法',
          high: { count: 0, total: 10 },
          items: [{ title: '收集品', unlock: false }],
          level: null,
        },
      },
    }),
  })
  for (const text of [
    '新的玩法',
    '高难进度',
    '数量 0',
    '总量 10',
    '收集品',
    '已解锁 否',
    '等级 未知',
  ])
    assert.ok(content(root).includes(text), text)
})
test('combat resolves ID-only teams through current account role names', async (t) => {
  const root = mount(t, await component('WuwaCombat'), {
    roleNames: { 1501: '今汐' },
    snap: snap({
      tower: {
        state: 'ok',
        data: {
          difficulty_list: [
            {
              difficulty: 3,
              tower_area_list: [
                { floor_list: [{ floor: 1, role_list: [{ role_id: 1501 }] }] },
              ],
            },
          ],
        },
      },
    }),
  })
  assert.match(content(root), /今汐/)
})
test('news-only snapshots stay accessible through Wuwa announcement tab', async (t) => {
  const root = mount(t, await component('WuwaDashboard'), {
    configured: true,
    snaps: {
      account,
      news: snap([
        {
          title: 'B站合并公告',
          url: 'https://example.com',
          published_at: '2026-09-16',
        },
      ]),
    },
  })
  await click(root, '公告')
  assert.match(content(root), /B站合并公告/)
})
test('account switch discards pending role and archive responses', async (t) => {
  const pending = []
  t.mock.method(
    globalThis,
    'fetch',
    (url) => new Promise((resolve) => pending.push({ url, resolve })),
  )
  const props = reactive({ accountKey: 'account:server' })
  const root = mount(t, await component('WuwaGacha'), props)
  await tick()
  props.accountKey = 'next:server'
  await tick()
  pending[0].resolve(
    reply({
      ...identity,
      total: 1,
      items: [{ name: '旧账号私密角色' }],
      gold: [],
      pools: [],
      coverage: {},
    }),
  )
  await tick()
  assert.doesNotMatch(content(root), /旧账号私密角色/)
  pending[1].resolve(
    reply({
      role_id: 'next',
      server_id: 'server',
      total: 0,
      items: [],
      gold: [],
      pools: [],
      coverage: {},
    }),
  )
  await tick()
  assert.match(content(root), /全档案 0 抽/)
})
test('file import reads local JSON only after explicit click and masks error response', async (t) => {
  const requests = []
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    requests.push({ url, options })
    return options?.method === 'POST'
      ? { ok: false, status: 422, json: async () => ({ detail: 'SECRET' }) }
      : reply({
          ...identity,
          total: 0,
          items: [],
          gold: [],
          pools: [],
          coverage: {},
        })
  })
  const root = mount(t, await component('WuwaGacha'), {
    accountKey: 'account:server',
  })
  await tick()
  const input = nodes(root, 'input').find((n) => n.props.type === 'file')
  let reads = 0
  input.props.onChange({
    target: {
      files: [
        {
          size: 50,
          text: async () => {
            reads++
            return JSON.stringify({ uid: 'account', list: [] })
          },
        },
      ],
    },
  })
  await tick()
  assert.equal(reads, 0)
  await click(root, '导入文件')
  assert.equal(reads, 1)
  assert.deepEqual(JSON.parse(requests[1].options.body), {
    records: { uid: 'account', list: [] },
  })
  assert.match(content(root), /参数无效/)
  assert.doesNotMatch(content(root), /SECRET/)
})
test('leaving gacha during file read cancels deferred import before it sends a POST', async (t) => {
  const requests = []
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    requests.push({ url, options })
    return reply({
      ...identity,
      total: 0,
      items: [],
      gold: [],
      pools: [],
      coverage: {},
    })
  })
  const root = mount(t, await component('WuwaDashboard'), {
    configured: true,
    snaps: { account },
  })
  await click(root, '抽卡历史')
  let finish
  const input = nodes(root, 'input').find((n) => n.props.type === 'file')
  input.props.onChange({
    target: {
      files: [
        { size: 50, text: () => new Promise((resolve) => (finish = resolve)) },
      ],
    },
  })
  await tick()
  await click(root, '导入文件')
  await click(root, '成长记录')
  finish('{"uid":"account","list":[]}')
  await tick()
  assert.equal(requests.filter((r) => r.options?.method === 'POST').length, 0)
})
test('resource responses cannot roll back a newer period selection', async (t) => {
  const pending = []
  t.mock.method(
    globalThis,
    'fetch',
    (url) => new Promise((resolve) => pending.push({ url, resolve })),
  )
  const root = mount(t, await component('WuwaResources'), {
    accountKey: 'account:server',
    snap: snap({
      periods: {
        week: [
          { period: '1', title: '第一周' },
          { period: '2', title: '第二周' },
        ],
      },
      current: null,
    }),
  })
  await click(root, '第一周')
  await click(root, '第二周')
  pending[1].resolve(
    reply({
      payload: {
        ...identity,
        kind: 'week',
        period: '2',
        data: { total_coin: 22, total_star: 0 },
      },
    }),
  )
  await tick()
  pending[0].resolve(
    reply({
      payload: {
        ...identity,
        kind: 'week',
        period: '1',
        data: { total_coin: 11, total_star: 0 },
      },
    }),
  )
  await tick()
  assert.match(content(root), /贝币 22/)
  assert.doesNotMatch(content(root), /贝币 11/)
})
