import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick, reactive } from 'vue'
import { loadVue, mount, nodes, content } from '../test-utils/vue.js'
import { prepareArticles } from '../articles.js'

const List = await loadVue(new URL('./AnnouncementList.vue', import.meta.url))
const click = async (root, label) => {
  const button = nodes(root, 'button').find(n => content(n) === label)
  assert.ok(button, label); button.props.onClick(); await nextTick()
}
const article = (title, body, extra = {}) => ({ title, body, summary: body?.slice(0, 20), url: 'https://example.com/' + encodeURIComponent(title), ...extra })

test('a new successful snapshot replaces old full or stale content of the same article', () => {
  for (const status of ['full', 'stale']) {
    const rows = prepareArticles([
      { stale: true, fetched_at: '2026-10-04T09:00:00Z', payload: [article('修订公告', '旧正文', { content_status: status })] },
      { fetched_at: '2026-10-04T10:00:00Z', payload: [article('修订公告', '新完整正文', { content_status: 'full' })] },
    ])
    assert.equal(rows.length, 1)
    assert.equal(rows[0].body, '新完整正文')
    assert.equal(rows[0].content_status, 'full')
    assert.equal(rows[0].source_stale, false)
  }
})

test('different same-source articles with the same heading remain distinct', () => {
  assert.equal(prepareArticles([{ payload: [article('维护通知', '第一篇', { id: '1', source: 'official', url: 'https://example.com/1' }), article('维护通知', '第二篇', { id: '2', source: 'official', url: 'https://example.com/2' })] }]).length, 2)
})

test('the first list shows excerpts and full text is only shown in details with its original link', async t => {
  const body = '活动介绍与参与条件。'.repeat(40) + '\n全文结尾奖励说明'
  const root = mount(t, List, { gameId: 'nte', snap: { payload: [article('游戏内限时活动', body, { content_status: 'full' })] } })
  assert.match(content(root), /活动介绍/)
  assert.doesNotMatch(content(root), /全文结尾奖励说明/)
  await click(root, '游戏内限时活动')
  assert.equal(nodes(root, 'dialog').length, 1)
  assert.match(content(nodes(root, 'dialog')[0]), /全文结尾奖励说明/)
  assert.equal(nodes(nodes(root, 'dialog')[0], 'a').find(n => content(n).includes('查看原文')).props.href, 'https://example.com/' + encodeURIComponent('游戏内限时活动'))
  await click(root, '关闭详情')
  assert.equal(nodes(root, 'dialog').length, 0)
  assert.match(content(root), /活动介绍/)
})

test('a mixed version article keeps its main category and carries optional content tags', async t => {
  const root = mount(t, List, { gameId: 'wuthering_waves', snap: { payload: [article('3.7版本内容说明', '角色活动唤取限时开启\n七日签到奖励说明', { content_status: 'full' }), article('模糊的最新消息', '')] } })
  assert.ok(nodes(root, 'button').some(n => content(n).startsWith('版本更新说明')))
  assert.ok(nodes(root, 'span').some(n => content(n) === '角色卡池'))
  assert.ok(nodes(root, 'span').some(n => content(n) === '签到福利'))
  assert.ok(nodes(root, 'button').some(n => content(n).startsWith('其他')))
  const filter = nodes(root, 'button').find(n => content(n).startsWith('版本更新说明'))
  filter.props.onClick(); await nextTick()
  assert.match(content(root), /3\.7版本内容说明/)
  assert.doesNotMatch(content(root), /模糊的最新消息/)
})

for (const [gameId, title, expected] of [
  ['nte', '「限定棋盘」返场公告', '角色卡池'],
  ['nte', '「行进」弧盘研募开启', '武器与装备卡池'],
  ['endfield', '「冬猎」特许寻访', '角色卡池'],
  ['endfield', '「武库申领」限时开放', '武器与装备卡池'],
  ['wuthering_waves', '「身赴三途」角色活动唤取', '角色卡池'],
  ['league_of_legends', '世界赛赛事日程公布', '赛事资讯'],
  ['nte', '创作征集网页活动开启', '社区活动'],
]) test(`${gameId} classifies ${title} by its article subject`, t => {
  const root = mount(t, List, { gameId, snap: { payload: [article(title, '正文说明')] } })
  assert.ok(nodes(root, 'button').some(n => content(n).startsWith(expected)), expected)
})

test('duplicate snapshots form one dated list and retain the fuller body and stale source state', async t => {
  const root = mount(t, List, { gameId: 'league_of_legends', snap: { payload: [article('更新维护通知', '', { published_at: '2026-10-01T00:00:00Z' })] }, extraSnaps: [{ stale: true, capability: 'announcement', payload: [article('更新维护通知', '保留的完整正文', { published_at: '2026-10-01T00:00:00Z', content_status: 'full' })] }] })
  assert.equal(nodes(root, 'button').filter(n => content(n) === '更新维护通知').length, 1)
  assert.match(content(root), /数据可能过期|旧记录/)
  await click(root, '更新维护通知')
  assert.match(content(nodes(root, 'dialog')[0]), /保留的完整正文/)
})

test('missing, video, external and failed content are explicit and unsafe URLs are never links', async t => {
  const root = mount(t, List, { snap: { payload: [article('视频资讯', '', { content_status: 'video' }), article('外链资讯', '', { content_status: 'external' }), article('失败资讯', '', { content_status: 'error', content_error: '正文暂时无法读取' }), article('未知资讯', '', { url: 'javascript:alert(1)' })] } })
  await click(root, '视频资讯'); assert.match(content(nodes(root, 'dialog')[0]), /视频/); await click(root, '关闭详情')
  await click(root, '外链资讯'); assert.match(content(nodes(root, 'dialog')[0]), /外部|外链/); await click(root, '关闭详情')
  await click(root, '失败资讯'); assert.match(content(nodes(root, 'dialog')[0]), /正文暂时无法读取/); await click(root, '关闭详情')
  await click(root, '未知资讯'); assert.match(content(nodes(root, 'dialog')[0]), /正文.*未|正文.*无法|暂无正文/)
  assert.ok(nodes(root, 'a').every(n => !n.props.href?.startsWith('javascript:')))
})

test('filtering and closing details preserve the list while snapshot replacement removes stale selected content', async t => {
  const props = reactive({ snap: { payload: [article('维护通知', '旧文章全文', { content_status: 'full' })] } })
  const root = mount(t, List, props)
  await click(root, '维护通知')
  props.snap = { payload: [] }; await nextTick()
  assert.equal(nodes(root, 'dialog').length, 0)
  assert.doesNotMatch(content(root), /旧文章全文/)
})
