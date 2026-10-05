import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick } from 'vue'
import { loadVue, mount, nodes, content } from '../test-utils/vue.js'
const Card = await loadVue(new URL('./GameCard.vue', import.meta.url))
const tick = async () => { await new Promise(setImmediate); await nextTick() }
for (const gameId of ['nte', 'wuthering_waves', 'endfield', 'league_of_legends']) {
  test(`${gameId} exposes one article list before opening a full-text detail`, async t => {
    const row = { title: '限时游戏内活动', body: '参与条件完整正文\n末段奖励', summary: '参与条件节选', url: 'https://example.com/42', content_status: 'full' }
    t.mock.method(globalThis, 'fetch', async url => new Response(JSON.stringify(url.endsWith('/public') ? { news: { items: [row] }, tools: [] } : { connected: false, roles: [], matches: [], coverage: { archived_games: 0 }, overview: { games: 0 } })))
    const root = mount(t, Card, { game: { game_id: gameId, display_name: gameId, capabilities: ['news', 'announcement'], credentials_configured: false }, externalSnapshots: { news: { payload: [row] }, announcement: { payload: [row] } }, initialSection: 'news' })
    await tick()
    if (gameId === 'league_of_legends') { const nav = nodes(root, 'button').find(n => content(n) === '公告与资讯'); assert.ok(nav, 'unified article navigation'); nav.props.onClick(); await tick() }
    assert.equal(nodes(root, 'button').filter(n => content(n) === row.title).length, 1)
    assert.equal(nodes(root, 'section').filter(n => n.props.class?.includes?.('article-list')).length, 1)
    assert.match(content(root), /参与条件节选/)
    assert.doesNotMatch(content(root), /末段奖励/)
    assert.equal(nodes(root, 'dialog').length, 0)
    assert.equal(nodes(root, 'a').filter(n => n.props.href === row.url).length, 1)
    nodes(root, 'button').find(n => content(n) === row.title).props.onClick(); await tick()
    assert.equal(nodes(root, 'dialog').length, 1)
    assert.match(content(nodes(root, 'dialog')[0]), /末段奖励/)
  })
}
