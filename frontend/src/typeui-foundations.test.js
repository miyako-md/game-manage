import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const srcDir = path.dirname(fileURLToPath(import.meta.url))
const read = (relativePath) => fs.readFileSync(path.join(srcDir, relativePath), 'utf8')

function listSourceFiles(dir = srcDir) {
  const results = []
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      results.push(...listSourceFiles(full))
    } else if ((entry.name.endsWith('.css') || entry.name.endsWith('.vue')) && !entry.name.endsWith('.test.js')) {
      results.push(full)
    }
  }
  return results
}

test('removes all side-colored accent borders and stripes across frontend/src', () => {
  const files = listSourceFiles()
  for (const file of files) {
    const content = fs.readFileSync(file, 'utf8')
    const rel = path.relative(srcDir, file)
    assert.doesNotMatch(content, /border-left\s*:\s*[2-9]\d*px\s+solid/i, `${rel} should not have thick border-left`)
    assert.doesNotMatch(content, /border-left-width\s*:\s*[2-9]\d*px/i, `${rel} should not have border-left-width >= 2px`)
    assert.doesNotMatch(content, /border-inline-start\s*:\s*[2-9]\d*px\s+solid/i, `${rel} should not have border-inline-start >= 2px`)
  }

  const labCss = read('qq-image/lab.css')
  assert.match(labCss, /\.chapter-mark\s*\{\s*display\s*:\s*none\s*;\s*\}/)

  const skinCss = read('qq-image/skin.css')
  assert.equal(skinCss.includes('border-left-color'), false)

  const skinEndfieldCss = read('qq-image/skin-endfield.css')
  assert.equal(skinEndfieldCss.includes('background-size: 8px 100%'), false)

  const helpSheet = read('qq-image/HelpSheet.vue')
  assert.equal(helpSheet.includes('inset 0 3px 0 var(--skin-accent)'), false)

  const timeline = read('components/CalendarTimelineContent.vue')
  assert.doesNotMatch(timeline, /\.timeline-event:not\(\.is-point\)::before\s*\{[^}]*width\s*:\s*3px/)
})

test('defines TypeUI foundation tokens and typography/interaction rules in style.css', () => {
  const style = read('style.css')

  // rem-units & control-alignment tokens
  assert.equal(style.includes('--fs-body: 0.8125rem;'), true)
  assert.equal(style.includes('--fs-page: 1.75rem;'), true)
  assert.equal(style.includes('--control-h: 40px;'), true)
  assert.equal(style.includes('--radius-segment: 11px;'), true)
  assert.equal(style.includes('--radius-dropdown-item: 10px;'), true)

  // input-styling & layered-shadow & backdrop-treatment tokens
  assert.equal(style.includes('--field-bg: #17181c;'), true)
  assert.equal(style.includes('--field-border: #32343a;'), true)
  assert.equal(style.includes('--field-bg: #fcfbf9;'), true)
  assert.equal(style.includes('--field-border: #dedcd7;'), true)
  assert.equal(style.includes('--dropdown-shadow:'), true)
  assert.equal(style.includes('--modal-shadow:'), true)
  assert.equal(style.includes('--scrim: rgba(0, 0, 0, .64);'), true)
  assert.equal(style.includes('--scrim: rgba(15, 18, 24, .42);'), true)

  // ligatures, monospace, text-wrap-balance, user-select
  assert.equal(style.includes('font-variant-ligatures: common-ligatures contextual;'), true)
  assert.equal(style.includes('font-variant-numeric:tabular-nums slashed-zero;'), true)
  assert.equal(style.includes('h1,h2,h3,h4 { text-wrap:balance; }'), true)
  assert.equal(style.includes('user-select:none;'), true)

  // optical-alignment, button-press, recognizable-links, hit-target
  assert.equal(style.includes('.ui-button:has(> svg:first-child) { padding-inline:12px 15px; }'), true)
  assert.equal(style.includes('transform:translateY(1px) scale(0.98);'), true)
  assert.equal(style.includes('text-underline-offset:3px;'), true)
  assert.equal(style.includes(".info-hint-trigger::before { content:''; position:absolute; inset:-12px; }"), true)

  // status-signal: offline indicator is a hollow ring, not a colour-only dot
  assert.equal(style.includes('.local-status i.offline { background:transparent; border:2px solid var(--danger); }'), true)
})

test('applies concentric radii, control alignment, and status signal shapes in components', () => {
  const menuSelect = read('components/MenuSelect.vue')
  assert.equal(menuSelect.includes('min-height: var(--control-h, 40px);'), true)
  assert.equal(menuSelect.includes('padding: 4px;'), true)
  assert.equal(menuSelect.includes('border-radius: var(--radius-dropdown-item, 10px);'), true)
  assert.equal(menuSelect.includes('box-shadow: var(--dropdown-shadow, var(--popover-shadow));'), true)

  const siteLogin = read('components/SiteLogin.vue')
  assert.equal(siteLogin.includes('border-radius:calc(var(--radius-shell) - 7px)'), true)

  const overview = read('components/OverviewPage.vue')
  assert.equal(overview.includes('.summary-state.warn i { border-radius:1.5px; transform:rotate(45deg); }'), true)

  const endfield = read('components/EndfieldDashboard.vue')
  assert.equal(endfield.includes('.ef-connection-dot { width:8px; height:8px; border-radius:50%; border:2px solid var(--text-faint); background:transparent; }'), true)
})
