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

// The obsidian overview (qq-image/lab.css) used these literals before it read the
// skin tokens; the Wuwa skin must reproduce them exactly so its image is unchanged.
const OBSIDIAN = {
  '--skin-bg': '#11131c', '--skin-bg-grad': 'linear-gradient(180deg, #161924 0%, #11131c 55%, #0d0f16 100%)',
  '--skin-surface': 'rgba(24, 28, 40, 0.85)', '--skin-line': 'rgba(214, 188, 138, 0.28)', '--skin-line-strong': 'rgba(214, 188, 138, 0.58)',
  '--skin-ink': '#f3f4f8', '--skin-muted': '#a5adbe', '--skin-accent': '#dfc38d', '--skin-accent-2': '#c8a362', '--skin-hot': '#ecd39f',
  '--skin-on-accent': '#161822', '--skin-radius-card': '16px', '--skin-radius-tile': '12px', '--skin-radius-chip': '999px',
  '--skin-glow': 'inset 0 0 24px rgba(214, 188, 138, 0.06)', '--skin-tint-rgb': '214, 188, 138',
}
const same = value => value.replace(/\b0\./g, '.').replace(/\s+/g, ' ').trim()

test('the Wuwa skin equals the former obsidian literals, which lab.css now reads as tokens', () => {
  const wuwa = block('wuwa')
  for (const [token, literal] of Object.entries(OBSIDIAN)) assert.equal(same(wuwa[token]), same(literal), token)
  const lab = readFileSync(new URL('./qq-image/lab.css', import.meta.url), 'utf8')
  const obsidian = lab.slice(lab.indexOf('.lab-sheet.is-account-overview {'))
  for (const literal of ['#11131c', '#f3f4f8', '#dfc38d', '#a5adbe', '#161822', 'rgba(214, 188, 138', 'rgba(24, 28, 40, 0.85)'])
    assert.ok(!obsidian.includes(literal), literal)
  assert.match(obsidian, /\.ao-game-block\[data-skin\] \{[^}]*--skin-surface: var\(--ao-shell-surface\)/)
})
