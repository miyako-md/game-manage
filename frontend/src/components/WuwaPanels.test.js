import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick, reactive } from 'vue'
import { loadVue, mount, content, nodes } from '../test-utils/vue.js'
import { configureHttpClient } from '../http-client.js'

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

test('history season heading converts UTC across Beijing midnight', async (t) => {
  t.mock.method(globalThis, 'fetch', async () =>
    reply({
      ...identity,
      total: 1,
      items: [
        {
          id: 1,
          season: '2026-10-11T20:00:00+00:00',
          payload: {},
          delta: null,
        },
      ],
    }),
  )
  const root = mount(t, await component('WuwaHistory'), {
    accountKey: 'account:server',
  })
  await tick()
  const heading = nodes(root, 'h3').find((n) => content(n).includes('赛季结束'))
  assert.match(content(heading), /2026-10-12.*04:00.*北京时间/)
  assert.doesNotMatch(content(heading), /2026-10-11|\+00:00/)
})

test('holograms group every difficulty inside their dialog without losing source status', async (t) => {
  const root = mount(t, await component('WuwaCombat'), {
    snap: snap({
      hologram: {
        state: 'stale',
        error: '保留旧记录',
        data: {
          challenge_info: {
            a: [
              { boss_name: '首领甲', difficulty: 1, pass_time: 123 },
              {
                boss_name: '首领甲',
                difficulty: 2,
                roles: [{ role_name: '今汐' }],
              },
            ],
            b: [{ boss_name: '首领乙', difficulty: 3 }],
          },
        },
      },
    }),
  })
  await click(root, '查看战术全息')
  const groups = nodes(root, 'details').filter((n) =>
    nodes(n, 'summary').some((s) => /首领[甲乙]/.test(content(s))),
  )
  assert.equal(groups.length, 2)
  assert.ok(groups.every((n) => !n.props.open))
  assert.match(content(nodes(groups[0], 'summary')[0]), /首领甲.*2 条记录/)
  assert.match(content(groups[0]), /难度 1/)
  assert.match(content(groups[0]), /难度 2/)
  assert.match(content(groups[0]), /通关时间 123/)
  assert.match(content(groups[0]), /今汐/)
  assert.match(content(root), /暂时无法读取.*重试/)
  assert.match(content(root), /旧数据/)
  assert.match(content(root), /冥歌海墟/)
})
test('tower floors omit unknown denominators and explain omitted caps once', async (t) => {
  const root = mount(t, await component('WuwaTower'), {
    data: {
      difficulty_list: [
        {
          difficulty: 3,
          tower_area_list: [
            {
              star: 6,
              max_star: 12,
              floor_list: [
                { floor: 1, star: 3 },
                { floor: 2, star: 0, max_star: null },
                { floor: 3, star: 2, max_star: 3 },
              ],
            },
          ],
        },
      ],
    },
  })
  assert.match(content(root), /已得 3 星/)
  assert.match(content(root), /已得 0 星/)
  assert.match(content(root), /2 \/ 3 星/)
  assert.doesNotMatch(content(root), /\/ 未知 星/)
  assert.equal(
    (content(root).match(/来源未提供部分楼层的星数上限/g) || []).length,
    1,
  )
})
test('profile uses confirmed crystal material terminology for stored resource fields', async (t) => {
  const root = mount(t, await component('WuwaProfile'), {
    snap: snap({
      extra: {
        profile: {
          store_energy: 0,
          store_energy_limit: 480,
          store_energy_title: '结晶单质',
        },
      },
    }),
  })
  assert.match(content(root), /结晶单质 0/)
  assert.match(content(root), /结晶单质上限 480/)
  assert.doesNotMatch(content(root), /储存波片/)
})

test('full detail keeps role, skin and set names but drops skill, chain, weapon and set effect text', async (t) => {
  const root = mount(t, await component('WuwaRoleDetail'), {
    data: {
      active_branch_id: 0,
      role: {
        role_name: '今汐',
        level: 80,
        breach: 6,
        chain_unlock_num: 0,
        star_level: 5,
        attribute_name: '衍射',
        weapon_type_name: '长刃',
        is_main_role: false,
        role_id: 1501,
        future_role_field: '角色补充值',
      },
      role_skin: {
        skin_name: '默认外观',
        quality_name: '典藏',
        quality: 5,
        is_addition: false,
        skin_id: 42,
        future_skin_field: '外观补充值',
      },
      weapon_data: {
        level: 90,
        weapon: { weapon_name: '合成武器', weapon_effect_name: '武器效果名', effect_description: '武器效果描述' },
        main_prop_list: [{ attribute_name: '攻击', attribute_value: '500' }],
      },
      skill_list: [
        {
          level: 10,
          active_branch: 1,
          skill: {
            name: '常态攻击',
            type: '常态攻击',
            description: '技能描述',
            skill_branches: [{ name: '分支甲', description: '分支描述' }],
          },
        },
      ],
      chain_list: [{ order: 1, name: '共鸣链甲', unlocked: true, description: '共鸣链描述', future_chain_field: '共鸣链补充值' }],
      phantom_data: {
        cost: 12,
        equip_phantom_list: [
          {
            main_props: [{ attribute_name: '暴击', attribute_value: '22%' }],
            sub_props: [{ attribute_name: '攻击', attribute_value: '30' }],
            phantom_prop: { name: '角', skill_description: '声骸技能描述', future_phantom_field: '声骸补充值' },
            fetter_detail: {
              name: '浮星祛暗',
              num: 0,
              group_id: 9,
              type: 1,
              first_description: '两件套效果',
              second_description: '五件套效果',
              future_set_field: '套装补充值',
            },
          },
        ],
      },
    },
  })
  for (const expected of [
    '角色基本信息',
    '武器类型 长刃',
    '已解锁共鸣链 0',
    '外观品质 典藏',
    '附加外观标记 否',
    '套装已装备 0 件',
    '角色补充值',
    '外观补充值',
    '合成武器',
    '攻击 500',
    '常态攻击',
    'Lv.10',
    '共鸣链甲',
    '已解锁',
    '暴击 22%',
    '攻击 30',
    '浮星祛暗',
  ])
    assert.ok(content(root).includes(expected), expected)
  for (const removed of [
    '武器效果',
    '技能描述',
    '分支',
    '共鸣链描述',
    '共鸣链补充值',
    '声骸技能',
    '声骸补充值',
    '套装补充值',
    '两件套效果',
    '五件套效果',
  ])
    assert.ok(!content(root).includes(removed), removed)
})

test('whole snapshot staleness remains visible when nested source states were once ok', async (t) => {
  const root = mount(t, await component('WuwaCombat'), {
    snap: {
      ...snap({ tower: { state: 'ok', data: { difficulty_list: [] } } }),
      stale: true,
    },
  })
  assert.ok(nodes(root, 'span').some(node => String(node.props.class).includes('badge-stale') && content(node) === '旧数据')); assert.match(content(root), /更新于 2026-09-16 12:00/)
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
  await click(root, '查看逆境深塔')
  assert.match(content(root), /深境测试/)
  assert.doesNotMatch(content(root), /不要默认显示/)
  assert.match(content(root), /0 \/ 3/)
  assert.match(content(root), /今汐/)
  const panel=title=>nodes(root,'section').find(node=>node.props.class?.includes('wuwa-panel') && nodes(node,'h2').some(heading=>content(heading)===title))
  const hologram=panel('战术全息')
  assert.ok(hologram)
  assert.match(content(hologram), /暂时无法读取.*重试/)
  assert.doesNotMatch(content(hologram), /来源请求失败/)
  assert.doesNotMatch(content(panel('逆境深塔')), /暂时无法读取|旧数据/)
  assert.match(content(panel('冥歌海墟')), /旧数据.*2026-09-15/)
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
      String(url).endsWith('/preview')
        ? { ...identity, preview_id:'url-ticket', received:result.received, new_records:0, duplicates:result.received, failed_pools:result.failed_pools }
        : options?.method === 'POST'
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
  await click(root, '预览链接')
  assert.equal(calls[1].options.headers['X-Game-Assistant'], '1')
  assert.equal(calls.filter(r=>String(r.url).endsWith('/import')).length,0)
  await click(root, '确认导入链接预览')
  assert.match(content(root), /新增 0/)
  assert.match(content(root), /收到 2/)
  assert.match(content(root), /9/)
  assert.equal(input.props.value, '')
  assert.doesNotMatch(content(root), /SECRET/)
  result = { inserted: 0, received: 0, failed_pools: [], state: 'need_import' }
  input.props.onInput({ target: { value: 'another' } })
  await click(root, '预览链接')
  await click(root, '确认导入链接预览')
  assert.match(content(root), /未获得记录/)
})
test('the gacha import says where the records are kept: this machine locally, the personal space in the cloud', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => reply({ ...identity, total: 0, items: [], gold: [], gold_total: 0, pools: [], state: 'need_import', coverage: { complete: false } }))
  t.after(() => configureHttpClient({ mode: 'local' }))
  for (const [mode, kept, other] of [['local', /记录保存在本机/, /当前账号/], ['cloud', /记录保存在当前账号/, /本机/]]) {
    configureHttpClient({ mode })
    const root = mount(t, await component('WuwaGacha'), { accountKey: 'account:server' })
    await tick()
    assert.match(content(root), kept)
    assert.doesNotMatch(content(root), other)
  }
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
  assert.match(content(root), /首次记录/)
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
  await click(root, '查看详情')
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
  await click(root, '查看逆境深塔')
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
  assert.match(content(root), /已导入记录 0 抽/)
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
  await click(root, '预览文件')
  assert.equal(reads, 1)
  assert.deepEqual(JSON.parse(requests[1].options.body), {
    records: { uid: 'account', list: [] },
    source: 'json_import', latest_confirmed: false, continuity_confirmed: false,
  })
  assert.match(content(root), /参数无效/)
  assert.doesNotMatch(content(root), /SECRET/)
})
test('file preview stays busy during the file read and requires a separate import confirmation', async (t) => {
  t.mock.method(globalThis, 'fetch', async () =>
    reply({
      ...identity,
      total: 0,
      items: [],
      gold: [],
      pools: [],
      coverage: {},
    }),
  )
  const root = mount(t, await component('WuwaGacha'), {
    accountKey: 'account:server',
  })
  await tick()
  const fileInput = () => nodes(root, 'input').find((n) => n.props.type === 'file')
  let finish
  fileInput().props.onChange({
    target: {
      files: [
        { size: 50, text: () => new Promise((resolve) => (finish = resolve)) },
      ],
    },
  })
  await tick()
  await click(root, '预览文件')
  assert.match(content(root), /正在读取 \/ 预览/)
  assert.equal(fileInput().props.disabled, true)
  finish('{"uid":"account","list":[]}')
  await tick()
  await tick()
  assert.doesNotMatch(content(root), /正在读取 \/ 预览/)
  assert.equal(fileInput().props.disabled, false)
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
  await click(root, '查看抽卡历史')
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
  await click(root, '预览文件')
  await click(root, '关闭详情')
  await click(root, '成长记录')
  finish('{"uid":"account","list":[]}')
  await tick()
  assert.equal(requests.filter((r) => r.options?.method === 'POST').length, 0)
})
test('file preview cannot commit before explicit confirmation and account switch clears its ticket', async (t) => {
  const requests=[]
  t.mock.method(globalThis,'fetch',async (url,options)=>{
    requests.push({url,options})
    if(String(url).endsWith('/preview'))return reply({...identity,preview_id:'bound-ticket',received:1,new_records:1,duplicates:0,import_kind:'per_draw'})
    if(String(url).endsWith('/import'))return reply({...identity,received:1,inserted:1,state:'imported'})
    return reply({...identity,total:0,items:[],gold:[],pools:[],coverage:{}})
  })
  const props=reactive({accountKey:'account:server'})
  const root=mount(t,await component('WuwaGacha'),props)
  await tick()
  const selectFile=()=>nodes(root,'input').find(n=>n.props.type==='file').props.onChange({target:{files:[{size:50,text:async()=>JSON.stringify({info:{uid:'account'},list:[]})}]}})
  selectFile();await click(root,'预览文件')
  assert.equal(requests.filter(r=>String(r.url).endsWith('/import')).length,0)
  await click(root,'确认导入本次预览')
  assert.deepEqual(JSON.parse(requests.find(r=>String(r.url).endsWith('/import')).options.body),{preview_id:'bound-ticket'})
  selectFile();await click(root,'预览文件')
  props.accountKey='other:server';await tick()
  assert.equal(nodes(root,'button').some(n=>content(n).includes('确认导入本次预览')),false)
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

test('a chosen resource period survives polling; a newer fetch replaces only the current period', async (t) => {
  const reports = {
    'week/7': { kind: 'week', period: '7', data: { total_coin: 7, total_star: 8 } },
    'month/202610': { kind: 'month', period: '202610', data: { total_coin: 111, total_star: 222 } },
  }
  t.mock.method(globalThis, 'fetch', async (url) => ({
    ok: true,
    json: async () => ({ payload: { ...identity, ...reports[url.split('/resources/')[1]] } }),
  }))
  const resources = (fetched_at, coin) => ({
    fetched_at, stale: false,
    payload: {
      periods: { week: [{ period: '7', title: '九月第二周' }], month: [{ period: '202610', title: '十月' }], version: [] },
      current: { kind: 'month', period: '202610', state: 'ok', data: { total_coin: coin, total_star: 222 } },
    },
  })
  const coin = (root) => content(root).match(/贝币 (\S+)/)?.[1]
  const props = reactive({ accountKey: 'account:server', snap: resources('2026-10-16T04:00:00Z', 111) })
  const root = mount(t, await component('WuwaResources'), props)
  await tick()
  await click(root, '九月第二周')
  assert.equal(coin(root), '7')
  props.snap = resources('2026-10-16T04:00:00Z', 111) // the 60-second re-read: same data, new object
  await tick()
  assert.equal(coin(root), '7')
  props.snap = resources('2026-10-16T05:00:00Z', 333) // a newer fetch of another period
  await tick()
  assert.equal(coin(root), '7')
  await click(root, '十月')
  props.snap = resources('2026-10-16T06:00:00Z', 444) // the period on display was fetched again
  await tick()
  assert.equal(coin(root), '444')
})

test('resource heading formats a month period and the image hides the generic category dump', async (t) => {
  const payload = (kind, period) => ({ fetched_at: '2026-10-16T04:00:00Z', stale: false, payload: { current: { kind, period, state: 'ok',
    data: { total_coin: 3244215, total_star: 5768, item_list: [{ type: 1, total: 3244215 }, { type: 4, total: 19 }] } } } })
  const Resources = await component('WuwaResources')
  const image = mount(t, Resources, { snap: payload('month', '202610'), imageMode: true })
  assert.match(content(image), /2026 年 10 月 · 期间获取/)
  assert.doesNotMatch(content(image), /月周期|全部资源类别|类别|3244215 /)
  const web = mount(t, Resources, { snap: payload('month', '202610') })
  assert.match(content(web), /2026 年 10 月 · 期间获取/); assert.match(content(web), /全部资源类别与明细/)
  assert.match(content(mount(t, Resources, { snap: payload('version', '3.7') })), /3\.7 版本 · 期间获取/)
  assert.match(content(mount(t, Resources, { snap: payload('week', '7') })), /周周期 7 · 期间获取/)
})
