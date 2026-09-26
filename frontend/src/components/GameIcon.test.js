import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, existsSync } from 'node:fs'
import { nextTick, reactive } from 'vue'
import { loadVue, mount, nodes, content } from '../test-utils/vue.js'
import { gameStyle } from '../dashboard.js'

const GameIcon = await loadVue(new URL('./GameIcon.vue', import.meta.url))
test('each supported game uses a locally bundled icon with recorded provenance', () => {
  const sources = JSON.parse(readFileSync(new URL('../../public/game-icons/sources.json', import.meta.url)))
  for (const id of ['league_of_legends', 'wuthering_waves', 'nte', 'endfield']) {
    const src = gameStyle(id).icon
    assert.match(src, /^\/game-icons\//)
    assert.ok(readFileSync(new URL(`../../public${src}`, import.meta.url)).length > 500)
    assert.equal(sources.find(item => item.game_id === id).file, src.split('/').at(-1))
    assert.equal(sources.find(item => item.game_id === id).license, 'GPL-3.0-only')
    const light = gameStyle(id).iconLight
    assert.ok(readFileSync(new URL(`../../public${light}`, import.meta.url)).length > 500)
    assert.equal(sources.find(item => item.game_id === id).file_light, light.split('/').at(-1))
  }
  for (const file of ['nte.jpg', 'wuthering_waves.jpg', 'league_of_legends.svg']) {
    assert.equal(existsSync(new URL(`../../public/game-icons/${file}`, import.meta.url)), false)
  }
})
test('icon failure falls back to game mark and a changed game retries its own icon', async (t) => {
  const props = reactive({ gameId: 'nte', name: '异环' })
  const root = mount(t, GameIcon, props)
  assert.equal(nodes(root, 'img')[0].props.alt, '异环图标')
  nodes(root, 'img')[0].props.onError()
  await nextTick()
  assert.equal(nodes(root, 'img').length, 0)
  assert.match(content(root), /异/)
  props.gameId = 'wuthering_waves'
  await nextTick()
  assert.equal(nodes(root, 'img')[0].props.src, gameStyle('wuthering_waves').icon)
})
