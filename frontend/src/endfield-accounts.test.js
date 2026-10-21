import test from 'node:test'
import assert from 'node:assert/strict'
import { resolveEndfieldSources, endfieldRoleChoices, endfieldFallback, endfieldFallbackCandidates, endfieldPageSources, endfieldSourceLabel } from './endfield-accounts.js'
const make = (provider, changes = {}) => ({ account_id: provider, provider, game: 'endfield', state: 'active', channel: 'bilibili', server: '1', user_id: 'user', roles: [{ role_id: `${provider}-opaque`, game_uid: '9001', display_name: 'same name' }], ...changes })
const sources = rows => resolveEndfieldSources(rows, rows[0], rows[0].roles[0].role_id)

test('a verified Bilibili character has one choice, canonical Hypergryph, from either source', () => {
  const h = make('hypergryph'), s = make('skland'), rows = [s, h]
  const resolved = sources(rows)
  assert.equal(resolved.hypergryph.account, h); assert.equal(resolved.hypergryph.role, 'hypergryph-opaque')
  assert.equal(resolved.skland.account, s); assert.equal(resolved.skland.role, 'skland-opaque')
  assert.deepEqual(endfieldRoleChoices(rows), [{ key: 'hypergryph:hypergryph-opaque', account: h, role: 'hypergryph-opaque', sources: resolved }])
})
for (const [name, changes] of Object.entries({
  uid: { roles: [{ role_id: 's', game_uid: '9002', display_name: 'same name' }] }, server: { server: '2' }, channel: { channel: 'official' },
  unknownChannel: { channel: 'unknown' }, missingServer: { server: '' }, owner: { user_id: 'another-user' }, inactive: { state: 'revoked' }, otherGame: { game: 'nte' },
})) test(`identity mismatch (${name}) cannot pair equal display names`, () => {
  const rows = [make('hypergryph'), make('skland', changes)]
  assert.deepEqual(Object.keys(sources(rows)), ['hypergryph'])
  assert.equal(endfieldRoleChoices(rows).length, name === 'otherGame' ? 1 : 2)
})
test('orphaned roles and ambiguous provider identities stay separate', () => {
  const h = make('hypergryph'), s = make('skland'), second = make('skland', { account_id: 'second' })
  assert.deepEqual(Object.keys(sources([h])), ['hypergryph'])
  assert.deepEqual(Object.keys(sources([h, s, second])), ['hypergryph'])
  assert.deepEqual(Object.keys(resolveEndfieldSources([h, s, second], s, s.roles[0].role_id)), ['skland'])
  assert.equal(endfieldRoleChoices([h, s, second]).length, 3)
})
test('legacy passport data needs one child role and an exact parent pointer with a known matching channel/server', () => {
  const h = make('hypergryph', { roles: [{ role_id: 'h' }] })
  const s = make('skland', { roles: [{ role_id: 's' }], authorization_source: 'passport', parent_account_id: h.account_id, parent_role_id: 'h' })
  assert.equal(endfieldRoleChoices([h, s]).length, 1)
  for (const changes of [{ parent_role_id: 'other' }, { parent_account_id: 'other' }, { authorization_source: 'manual' }, { channel: 'unknown' }, { roles: [{ role_id: 's' }, { role_id: 's2' }] }]) {
    assert.deepEqual(Object.keys(sources([h, { ...s, ...changes }])), ['hypergryph'])
  }
  const knownH = { ...h, roles: [{ role_id: 'h', game_uid: '1' }] }, knownS = { ...s, roles: [{ role_id: 's', game_uid: '2' }] }
  assert.equal(endfieldRoleChoices([knownH, knownS]).length, 2, 'a parent pointer must not override conflicting verified UIDs')
})
test('a stale selection and inactive grants never resolve a usable source', () => {
  const h = make('hypergryph')
  assert.deepEqual(resolveEndfieldSources([], h, h.roles[0].role_id), {})
  assert.deepEqual(resolveEndfieldSources([{ ...h, state: 'revoked' }], h, h.roles[0].role_id), {})
  assert.deepEqual(resolveEndfieldSources([h], h, 'unknown-role'), {})
})

test('other games are absent from Endfield choices; legacy provider-only Endfield rows remain usable', () => {
  const h = make('hypergryph'), s = make('skland')
  delete h.game; delete s.game
  const other = [{ account_id: 'k', provider: 'kuro', roles: [{ role_id: 'kr' }] }, { account_id: 't', provider: 'tajiduo', game: 'nte', roles: [{ role_id: 'tr' }] }]
  assert.equal(endfieldRoleChoices([h, s, ...other]).length, 1)
  assert.equal(resolveEndfieldSources([h, s], h, h.roles[0].role_id).skland.account, s)
  assert.equal(endfieldRoleChoices(other).length, 0)
})

const choiceOf = (rows, row) => endfieldRoleChoices(rows).find(choice => Object.values(choice.sources).some(source => source.account === row))
test('an unpaired entry borrows the missing provider only from the unique single-provider entry of the other side', () => {
  const h = make('hypergryph', { channel: 'official' }), s = make('skland', { channel: 'unknown' }), rows = [h, s]
  assert.equal(endfieldRoleChoices(rows).length, 2)
  assert.equal(endfieldFallback(endfieldRoleChoices(rows), choiceOf(rows, h), 'skland').account, s)
  assert.equal(endfieldFallback(endfieldRoleChoices(rows), choiceOf(rows, s), 'hypergryph').account, h)
  assert.equal(endfieldFallback(endfieldRoleChoices(rows), choiceOf(rows, h), 'hypergryph'), null, 'a provider the entry already has is never replaced')
  assert.equal(endfieldFallback(endfieldRoleChoices(rows), choiceOf(rows, h), 'kuro'), null)
  assert.equal(endfieldFallback(endfieldRoleChoices([h]), choiceOf([h], h), 'skland'), null)
  const paired = [h, { ...s, channel: 'official' }]
  assert.equal(endfieldFallback(endfieldRoleChoices(paired), endfieldRoleChoices(paired)[0], 'skland'), null, 'a merged entry needs no fallback')
  const missingUid = make('skland', { channel: 'unknown', roles: [{ role_id: 's' }] })
  assert.equal(endfieldFallback(endfieldRoleChoices([h, missingUid]), choiceOf([h, missingUid], h), 'skland').account, missingUid)
})
test('several candidates, another character\'s merged pair and a proven different role give no fallback', () => {
  const h = make('hypergryph', { channel: 'official' }), s = make('skland', { channel: 'unknown' }), s2 = make('skland', { account_id: 'second', channel: 'unknown' })
  const rows = [h, s, s2], current = choiceOf(rows, h)
  assert.equal(endfieldFallback(endfieldRoleChoices(rows), current, 'skland'), null)
  assert.deepEqual(endfieldFallbackCandidates(endfieldRoleChoices(rows), current, 'skland').map(choice => choice.account.account_id), ['skland', 'second'])
  const otherH = make('hypergryph', { account_id: 'other', channel: 'official', roles: [{ role_id: 'o', game_uid: '9002' }] })
  const otherS = make('skland', { account_id: 'other-s', channel: 'official', roles: [{ role_id: 'os', game_uid: '9002' }] })
  assert.equal(endfieldFallback(endfieldRoleChoices([h, otherH, otherS]), choiceOf([h, otherH, otherS], h), 'skland'), null)
  for (const changes of [{ roles: [{ role_id: 's', game_uid: '9002' }] }, { channel: 'bilibili' }, { server: '2' }, { user_id: 'another-user' }]) {
    const different = make('skland', changes), list = [h, different]
    assert.equal(endfieldFallback(endfieldRoleChoices(list), choiceOf(list, h), 'skland'), null, JSON.stringify(changes))
  }
  assert.deepEqual(endfieldFallbackCandidates(endfieldRoleChoices(rows), undefined, 'skland'), [])
})
test('page sources flag the borrowed provider and leave paired or ambiguous selections as resolved', () => {
  const h = make('hypergryph', { channel: 'official' }), s = make('skland', { channel: 'unknown' })
  const page = endfieldPageSources([h, s], h, h.roles[0].role_id)
  assert.equal(page.hypergryph.account, h); assert.equal(page.hypergryph.fallback, undefined)
  assert.equal(page.skland.account, s); assert.equal(page.skland.role, 'skland-opaque'); assert.equal(page.skland.fallback, true)
  const paired = [make('hypergryph'), make('skland')]
  assert.deepEqual(endfieldPageSources(paired, paired[0], 'hypergryph-opaque'), resolveEndfieldSources(paired, paired[0], 'hypergryph-opaque'))
  const ambiguous = [h, s, make('skland', { account_id: 'second', channel: 'unknown' })]
  assert.deepEqual(Object.keys(endfieldPageSources(ambiguous, h, h.roles[0].role_id)), ['hypergryph'])
  assert.deepEqual(endfieldPageSources([h], h, 'unknown-role'), {})
  assert.deepEqual(endfieldPageSources([{ account_id: 'k', provider: 'kuro', roles: [{ role_id: 'kr' }] }], { account_id: 'k', provider: 'kuro' }, 'kr'), {})
  assert.equal(endfieldSourceLabel(page.skland), 'same name · 渠道未提供')
  assert.equal(endfieldSourceLabel(page.hypergryph), 'same name · 官服')
})
