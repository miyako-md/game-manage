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
    } else if (entry.name.endsWith('.css') || entry.name.endsWith('.vue')) {
      results.push(full)
    }
  }
  return results
}

// Guards the design rule itself (no thick side-colored accent stripes), not the exact text of any rule.
test('no thick side-colored accent borders or stripes anywhere in frontend/src', () => {
  for (const file of listSourceFiles()) {
    const content = fs.readFileSync(file, 'utf8')
    const rel = path.relative(srcDir, file)
    assert.doesNotMatch(content, /border-left\s*:\s*[2-9]\d*px\s+solid/i, `${rel} should not have thick border-left`)
    assert.doesNotMatch(content, /border-left-width\s*:\s*[2-9]\d*px/i, `${rel} should not have border-left-width >= 2px`)
    assert.doesNotMatch(content, /border-inline-start\s*:\s*[2-9]\d*px\s+solid/i, `${rel} should not have border-inline-start >= 2px`)
  }
  assert.doesNotMatch(read('qq-image/Panel.vue'), /chapter-mark/)
  assert.doesNotMatch(read('qq-image/skin.css'), /border-left-color/)
  assert.doesNotMatch(read('qq-image/skin-endfield.css'), /background-size\s*:\s*8px\s+100%/)
  assert.doesNotMatch(read('qq-image/HelpSheet.vue'), /inset\s+0\s+[2-9]px\s+0\s+var\(--skin-accent\)/)
  const timeline = read('components/CalendarTimelineContent.vue')
  assert.doesNotMatch(timeline, /\.timeline-event:not\(\.is-point\)::before\s*\{[^}]*width\s*:\s*[2-9]px/)
  assert.doesNotMatch(timeline, /\.timeline-event\.clipped-end::after/)
  assert.doesNotMatch(timeline, /\.timeline-event\.is-short::after/, 'short bars carry no extra end stripe')
})

test('style.css defines the shared TypeUI foundation tokens', () => {
  const style = read('style.css')
  for (const token of ['--fs-body', '--fs-page', '--control-h', '--control-h-sm', '--radius-control', '--radius-segment', '--radius-dropdown-item',
    '--field-bg', '--field-border', '--dropdown-shadow', '--modal-shadow', '--scrim'])
    assert.match(style, new RegExp(`${token}\\s*:`), `${token} is not defined`)
})

test('chips stay selectable so UIDs can be copied, while controls do not select on click', () => {
  const style = read('style.css')
  const rule = style.match(/^([^{}\n]*)\{[^}]*user-select\s*:\s*none/m)
  assert.ok(rule, 'controls keep user-select:none')
  const selectors = rule[1].split(',').map(selector => selector.trim())
  for (const control of ['button', '[role="tab"]']) assert.ok(selectors.includes(control), `${control} should not select on click`)
  assert.ok(!selectors.includes('.chip'), 'UID chips must stay copyable')
  assert.match(read('components/NteDataCard.vue'), /class="chip mono">UID /)
})

test('the top bar search field is as tall as the 44px controls beside it', () => {
  const style = read('style.css')
  assert.match(style, /\.workspace-topbar\s*\{[^}]*--topbar-control-size\s*:\s*44px/)
  assert.match(style, /\.topbar-left\s*>\s*\.search-trigger\s*\{[^}]*[\s;{]height\s*:\s*var\(--topbar-control-size\)/)
  assert.match(style, /\.topbar-right\s*>\s*:is\([^)]*\.icon-button[^)]*\)\s*\{[^}]*height\s*:\s*var\(--topbar-control-size\)/)
})
