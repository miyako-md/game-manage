import test from 'node:test'
import assert from 'node:assert/strict'

test('a theme picked this session outlasts a system change even when storage is blocked', async t => {
  let systemChanged
  const blocked = () => { throw new Error('storage blocked') }
  globalThis.localStorage = { getItem: blocked, setItem: blocked }
  globalThis.matchMedia = () => ({ matches: true, addEventListener: (_, fn) => { systemChanged = fn }, removeEventListener() {} })
  t.after(() => { delete globalThis.localStorage; delete globalThis.matchMedia })
  const { theme, setTheme, followSystem } = await import('./theme.js')
  const stop = followSystem()
  systemChanged()
  assert.equal(theme.value, 'light', 'with no pick yet the system setting wins')
  setTheme('dark')
  systemChanged()
  assert.equal(theme.value, 'dark')
  stop()
})
