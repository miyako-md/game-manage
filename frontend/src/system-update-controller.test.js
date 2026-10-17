import test from 'node:test'
import assert from 'node:assert/strict'
import { HttpError } from './http-client.js'
import { canApplySystemUpdate, createSystemUpdateController, systemUpdateReason, systemUpdateStatus, updateIsVerified } from './system-update-controller.js'

const OLD = '1'.repeat(40), TARGET = '2'.repeat(40), NEW = '3'.repeat(40)
const snapshot = extra => ({ repository: 'miyako-md/game-manage', branch: 'main',
  current: { sha: OLD, frontend_sha: OLD, dirty: false }, latest: { sha: TARGET, message: '版本改进', committed_at: '2026-10-18T01:00:00Z' },
  relation: 'ahead', checked_at: 100, check_error: null, stale: false, can_apply: true, unavailable_reason: null,
  job: null, worker_available: true, ...extra })
const job = (phase, extra) => ({ job_id: 'update-one', phase, target_sha: TARGET, previous_sha: OLD, updated_at: 100, ...extra })
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no }); return { promise, resolve, reject } }
const settle = () => new Promise(resolve => setImmediate(resolve))
function harness(t, overrides = {}) {
  let time = 0, next = 0, invalidation = null
  const timers = new Map(), calls = []
  const api = Object.fromEntries(['get', 'check', 'apply'].map(name => [name, async (...args) => {
    calls.push({ name, args }); return overrides[name] ? overrides[name](...args) : snapshot()
  }]))
  const controller = createSystemUpdateController({ api, now: () => time,
    setTimer(fn, delay) { timers.set(++next, { fn, at: time + delay, delay }); return next }, clearTimer(id) { timers.delete(id) },
    subscribe(callback) { invalidation = callback; return () => { invalidation = null } },
  })
  const tick = async amount => {
    const until = time + amount
    while (true) {
      const first = [...timers].filter(([, timer]) => timer.at <= until).sort((a, b) => a[1].at - b[1].at)[0]
      if (!first) break
      time = first[1].at; timers.delete(first[0]); first[1].fn(); await settle()
    }
    time = until; await settle()
  }
  t.after(controller.destroy)
  return { ...controller, calls, timers, tick, invalidate() { invalidation?.() }, jump(amount) { time += amount } }
}

test('nothing runs until opening; opening reads status without checking or applying', async t => {
  const c = harness(t)
  assert.equal(c.calls.length, 0); assert.equal(c.timers.size, 0)
  await c.start()
  assert.deepEqual(c.calls.map(call => call.name), ['get'])
  assert.equal(c.timers.size, 0)
  assert.equal(canApplySystemUpdate(c.state), true)
})

test('explicit check refreshes the candidate; current-ahead and missing helper never enable an update', async t => {
  const c = harness(t, { get: () => snapshot({ latest: null, relation: 'unknown', checked_at: null, stale: true, can_apply: false }), check: () => snapshot() })
  await c.start(); assert.equal(canApplySystemUpdate(c.state), false)
  assert.match(systemUpdateStatus(c.state), /尚未取得版本信息/)
  await c.check(); assert.equal(canApplySystemUpdate(c.state), true)
  for (const value of [snapshot({ relation: 'behind' }), snapshot({ worker_available: false, can_apply: false, unavailable_reason: 'worker_unavailable' })]) {
    const other = harness(t, { get: () => value })
    await other.start(); await other.apply(TARGET)
    assert.equal(canApplySystemUpdate(other.state), false)
    assert.equal(other.calls.some(call => call.name === 'apply'), false)
  }
  const ahead = harness(t, { get: () => snapshot({ relation: 'behind' }) })
  await ahead.start(); assert.match(systemUpdateStatus(ahead.state), /当前版本领先主分支/)
  assert.match(systemUpdateReason('worker_unavailable'), /更新助手尚未运行/)
  assert.match(systemUpdateReason('preview_only'), /模拟预览中不会更新程序/)
})

test('a failed check retains the old version, marks it stale and blocks apply until a fresh successful check', async t => {
  let fail = true
  const c = harness(t, { check: () => snapshot({ checked_at: 101, stale: fail, check_error: fail ? 'github_unavailable' : null, can_apply: !fail }) })
  await c.start(); await c.check()
  assert.equal(c.state.snapshot.latest.sha, TARGET)
  assert.equal(canApplySystemUpdate(c.state), false)
  assert.match(systemUpdateStatus(c.state), /过期/)
  fail = false; await c.check()
  assert.equal(canApplySystemUpdate(c.state), true)
})

test('failed transport during a check confirms with GET, retaining a local stale marker for unchanged information', async t => {
  const c = harness(t, { check: () => { throw new TypeError('lost') } })
  await c.start(); await c.check()
  assert.deepEqual(c.calls.map(call => call.name), ['get', 'check', 'get'])
  assert.equal(c.state.snapshot.latest.sha, TARGET)
  assert.equal(c.state.checkFailed, true)
  assert.equal(canApplySystemUpdate(c.state), false)
})

test('apply sends the exact current and confirmed target commits, and repeated clicks cannot submit twice', async t => {
  const pending = deferred()
  const c = harness(t, { apply: () => pending.promise })
  await c.start()
  const first = c.apply(TARGET)
  await c.apply(TARGET); await c.check()
  assert.equal(c.calls.filter(call => call.name === 'apply').length, 1)
  assert.deepEqual(c.calls.find(call => call.name === 'apply').args[0], { expected_sha: OLD, target_sha: TARGET })
  pending.resolve(snapshot({ job: job('queued'), can_apply: false })); await first
  assert.equal(c.state.uncertain, false)
  assert.ok([...c.timers.values()].some(timer => timer.delay === 2000))
})

test('a target changed after confirmation is rejected without a mutation', async t => {
  const c = harness(t, { get: () => snapshot({ latest: { sha: NEW } }) })
  await c.start(); await c.apply(TARGET)
  assert.equal(c.calls.some(call => call.name === 'apply'), false)
  assert.match(c.state.error, /版本已变化/)
})

test('a lost apply response is confirmed by GET without retrying POST', async t => {
  let reads = 0
  const c = harness(t, { get: () => ++reads === 1 ? snapshot() : snapshot({ job: job('preparing'), can_apply: false }), apply: () => { throw new TypeError('response lost') } })
  await c.start(); await c.apply(TARGET)
  assert.deepEqual(c.calls.map(call => call.name), ['get', 'apply', 'get'])
  assert.equal(c.state.uncertain, false)
  assert.equal(c.state.snapshot.job.phase, 'preparing')
  await c.tick(2000)
  assert.equal(c.calls.filter(call => call.name === 'apply').length, 1)
})

test('missing or unrelated jobs do not confirm a lost update request', async t => {
  let reads = 0
  const c = harness(t, { get: () => ++reads < 3 ? snapshot() : snapshot({ job: job('completed', { target_sha: NEW }) }), apply: () => { throw new TypeError('response lost') } })
  await c.start(); await c.apply(TARGET)
  assert.equal(c.state.uncertain, true)
  assert.equal(canApplySystemUpdate(c.state), false)
  await c.tick(2000)
  assert.equal(c.state.uncertain, true)
  assert.equal(updateIsVerified(c.state), false)
  assert.equal(c.calls.filter(call => call.name === 'apply').length, 1)
})

test('restart disconnection retries reads after four seconds and only a matching running commit is completed', async t => {
  let reads = 0
  const c = harness(t, { get: () => {
    reads++
    if (reads === 1) return snapshot({ job: job('restarting'), can_apply: false })
    if (reads === 2) throw new TypeError('service restarting')
    if (reads === 3) return snapshot({ job: job('completed'), current: { sha: TARGET, frontend_sha: OLD }, can_apply: false })
    return snapshot({ job: job('completed'), current: { sha: TARGET, frontend_sha: TARGET }, can_apply: false })
  } })
  await c.start(); await c.tick(2000)
  assert.equal(c.state.connectionLost, true)
  assert.match(systemUpdateStatus(c.state), /等待服务恢复/)
  assert.equal(updateIsVerified(c.state), false)
  await c.tick(3999); assert.equal(reads, 2)
  await c.tick(1); assert.equal(reads, 3)
  assert.equal(updateIsVerified(c.state), false)
  assert.equal(canApplySystemUpdate(c.state), false)
  assert.match(systemUpdateStatus(c.state), /正在核对/)
  await c.tick(2000)
  assert.equal(updateIsVerified(c.state), true)
  assert.equal(c.timers.size, 0)
})

test('a claimed completion with an old backend commit keeps polling', async t => {
  const c = harness(t, { get: () => snapshot({ job: job('completed'), current: { sha: OLD, frontend_sha: TARGET } }) })
  await c.start()
  assert.equal(updateIsVerified(c.state), false)
  assert.equal(canApplySystemUpdate(c.state), false)
  assert.ok(c.timers.size)
})

test('a long restart stops automatic polling after twenty minutes, leaving a manual status read', async t => {
  const c = harness(t, { get: () => snapshot({ job: job('restarting'), can_apply: false }) })
  await c.start(); c.jump(20 * 60 * 1000)
  await c.tick(2000)
  assert.equal(c.state.timedOut, true)
  assert.equal(c.timers.size, 0)
  assert.match(systemUpdateStatus(c.state), /手动检查/)
  await c.retryStatus()
  assert.equal(c.state.timedOut, false)
  assert.ok(c.timers.size)
})

test('closing aborts in-flight reads, cancels timers and ignores a transport that resolves after disposal', async t => {
  const pending = deferred()
  const c = harness(t, { get: () => pending.promise })
  const start = c.start()
  const signal = c.calls[0].args[0].signal
  c.destroy()
  assert.equal(signal.aborted, true)
  assert.equal(c.timers.size, 0)
  pending.resolve(snapshot()); await start
  assert.equal(c.state.snapshot, null)
  await c.tick(30000)
  assert.equal(c.calls.length, 1)
})

test('session invalidation clears all private state and refuses further reads or apply in that dialog', async t => {
  const c = harness(t, { get: () => snapshot({ job: job('queued'), can_apply: false }) })
  await c.start(); assert.ok(c.timers.size)
  c.invalidate()
  assert.equal(c.state.snapshot, null)
  assert.equal(c.state.sessionEnded, true)
  assert.equal(c.timers.size, 0)
  await c.read(); await c.check(); await c.apply(TARGET)
  assert.equal(c.calls.length, 1)
})

test('unknown or malformed status never enables apply and failure/recovery states never look complete', async t => {
  const broken = harness(t, { get: () => ({ can_apply: true }) })
  await broken.start()
  assert.equal(broken.state.snapshot, null)
  assert.equal(canApplySystemUpdate(broken.state), false)
  for (const phase of ['failed', 'rolled_back', 'recovery_required']) {
    const c = harness(t, { get: () => snapshot({ job: job(phase), can_apply: false }) })
    await c.start()
    assert.equal(updateIsVerified(c.state), false)
    assert.equal(c.timers.size, 0)
    assert.doesNotMatch(systemUpdateStatus(c.state), /^更新完成/)
  }
})


test('a revoked administrator permission ends polling instead of pretending the service is restarting', async t => {
  let reads = 0
  const c = harness(t, { get: () => {
    if (++reads === 1) return snapshot({ job: job('verifying'), can_apply: false })
    // GET carries no CSRF mutation: even an unlabelled 403 is an access denial.
    throw new HttpError(403)
  } })
  await c.start(); await c.tick(2000)
  assert.equal(c.state.snapshot, null)
  assert.equal(c.state.sessionEnded, true)
  assert.equal(c.state.operation, '')
  assert.equal(c.state.connectionLost, false)
  assert.equal(c.state.uncertain, false)
  assert.equal(c.timers.size, 0)
  assert.match(systemUpdateStatus(c.state), /管理员权限已失效/)
  assert.doesNotMatch(systemUpdateStatus(c.state), /等待服务恢复/)
  assert.equal(canApplySystemUpdate(c.state), false)
  await c.read(); await c.check(); await c.apply(TARGET); await c.retryStatus(); await c.tick(30000)
  assert.deepEqual(c.calls.map(call => call.name), ['get', 'get'])
})

test('an expired website session stops status reads and asks for login', async t => {
  const c = harness(t, { get: () => { throw new HttpError(401) } })
  await c.start()
  assert.equal(c.state.snapshot, null)
  assert.equal(c.state.sessionEnded, true)
  assert.equal(c.state.connectionLost, false)
  assert.equal(c.timers.size, 0)
  assert.match(systemUpdateStatus(c.state), /会话已失效.*重新登录/)
  await c.retryStatus(); await c.tick(30000)
  assert.equal(c.calls.length, 1)
})


test('worker reasons identify actionable causes without inventing a network failure or a running old service', () => {
  for (const [code, expected] of [
    ['command_unavailable_or_timed_out', /工具不可用或执行超时/],
    ['command_failed', /更新步骤执行失败/],
    ['frontend_commit_mismatch', /构建未通过校验.*原服务尚未切换/],
    ['required_lockfile_missing', /缺少构建所需文件.*原服务尚未切换/],
    ['unsupported_cloud_data_layout', /云端数据目录布局暂不支持/],
    ['unsupported_local_data_path', /本地数据存放位置暂不支持/],
    ['linked_data_file', /链接文件.*不能自动备份/],
    ['browser_runtime_upgrade_requires_operator', /浏览器运行环境需要升级.*管理员/],
    ['render_runtime_missing', /浏览器或字体不可用/],
    ['official_main_changed', /主分支在检查后已有变化.*重新检查/],
    ['current_version_changed', /当前安装版本已变化.*重新读取/],
    ['current_not_ancestor', /无法直接升级到目标版本/],
    ['operator_recovery_required', /尚待恢复.*管理员/],
    ['rollback_health_failed', /恢复原版本后仍未通过运行检查/],
  ]) assert.match(systemUpdateReason(code), expected, code)
  for (const code of ['command_failed', 'command_unavailable_or_timed_out', 'service_did_not_stop',
    'service_did_not_start', 'new_release_health_failed', 'worker_interrupted', 'update_operation_failed']) {
    assert.doesNotMatch(systemUpdateReason(code), /网络|旧服务.*运行|原服务.*运行|已恢复原版本/, code)
  }
  assert.equal(systemUpdateReason('bad_code /private/data token=secret'), '暂时无法更新，请重新检查状态。')
  assert.equal(systemUpdateReason(null), '')
})
