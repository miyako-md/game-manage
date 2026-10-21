import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { SKIN_KEYS, SKIN_TOKENS, skinOf } from './game-themes.js'

const css = readFileSync(new URL('./game-themes.css', import.meta.url), 'utf8')
const block = key => {
  const body = css.split(`[data-skin="${key}"] {`)[1].split('}')[0]
  return Object.fromEntries([...body.matchAll(/(--[\w-]+):\s*([^;]+);/g)].map(m => [m[1], m[2].trim()]))
}
const rgb = value => {
  const hex = value.match(/^#([0-9a-f]{6})$/i)
  if (hex) return [0, 2, 4].map(i => parseInt(hex[1].slice(i, i + 2), 16))
  const [r, g, b, a = 1] = value.match(/[\d.]+/g).map(Number)
  return [r, g, b, a]
}
// Translucent surfaces are judged where they sit: composited over the skin background.
const over = (top, base) => { const [r, g, b, a = 1] = rgb(top); return [r, g, b].map((c, i) => c * a + base[i] * (1 - a)) }
const luminance = c => { const [r, g, b] = c.map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4 }); return 0.2126 * r + 0.7152 * g + 0.0722 * b }
const contrast = (a, b) => { const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05) }

test('every game skin defines the full token set and maps from its game id', () => {
  assert.deepEqual([skinOf('wuthering_waves'), skinOf('nte'), skinOf('endfield'), skinOf('league_of_legends')], ['wuwa', 'nte', 'endfield', null])
  for (const key of SKIN_KEYS) assert.deepEqual(Object.keys(block(key)).sort(), [...SKIN_TOKENS].sort())
})

test('skin text colours stay readable on the skin background and surface', () => {
  for (const key of SKIN_KEYS) {
    const values = block(key), bg = rgb(values['--skin-bg']), surface = over(values['--skin-surface'], bg)
    for (const token of ['--skin-ink', '--skin-muted', '--skin-accent', '--skin-accent-2'])
      for (const base of [bg, surface]) assert.ok(contrast(rgb(values[token]), base) >= 4.5, `${key} ${token}`)
    assert.ok(contrast(bg, rgb(values['--skin-accent'])) >= 4.5, `${key} on-accent`)
  }
})
