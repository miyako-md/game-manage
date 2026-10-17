import test from 'node:test'
import assert from 'node:assert/strict'
import { buildVersion } from '../build-version.js'

test('release builds use the pinned commit instead of the surrounding checkout', () => {
  const commit = 'a'.repeat(40)
  assert.deepEqual(buildVersion('.', { GA_BUILD_COMMIT: commit, VITE_SERVICE_MODE: 'cloud', PRIVATE_TOKEN: 'not-for-output' }, () => 'b'.repeat(40)), {
    schema: 1, source: 'miyako-md/game-manage', commit, mode: 'cloud',
  })
  assert.throws(() => buildVersion('.', { GA_BUILD_COMMIT: 'main' }), /full commit SHA/)
  assert.throws(() => buildVersion('.', { GA_BUILD_COMMIT: '' }), /full commit SHA/)
})

test('normal checkouts record their commit and archives keep unknown versions explicit', () => {
  assert.equal(buildVersion('.', {}, () => 'b'.repeat(40) + '\n').commit, 'b'.repeat(40))
  assert.equal(buildVersion('.', {}, () => { throw new Error('no Git metadata') }).commit, null)
  assert.equal(buildVersion('.', {}, () => 'not a revision').commit, null)
  assert.equal(buildVersion('.', {}).mode, 'local')
})
