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
})

test('style.css defines the shared TypeUI foundation tokens', () => {
  const style = read('style.css')
  for (const token of ['--fs-body', '--fs-page', '--control-h', '--control-h-sm', '--radius-control', '--radius-segment', '--radius-dropdown-item',
    '--field-bg', '--field-border', '--dropdown-shadow', '--modal-shadow', '--scrim'])
    assert.match(style, new RegExp(`${token}\s*:`), `${token} is not defined`)
})
