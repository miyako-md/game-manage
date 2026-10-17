import { reactive } from 'vue'
import { subscribeSessionInvalidation } from './http-client.js'
import { getSystemUpdate, checkSystemUpdate, applySystemUpdate } from './system-update-api.js'

export const UPDATE_PHASES = {
  queued: '更新已排队', preparing: '正在准备更新', stopping: '正在停止服务', backing_up: '正在备份当前版本',
  activating: '正在切换到新版本', restarting: '正在启动服务', verifying: '正在核对新版本',
  completed: '更新完成', failed: '更新失败', rolled_back: '更新未完成，已恢复原版本', recovery_required: '更新需要人工处理',
}
const ACTIVE = new Set(['queued', 'preparing', 'stopping', 'backing_up', 'activating', 'restarting', 'verifying'])
const SHA = /^[a-f0-9]{40}$/i
const RELATIONS = new Set(['unknown', 'up_to_date', 'ahead', 'behind', 'diverged'])
const MAX_WAIT = 20 * 60 * 1000
const REASONS = {
  preview_only: '模拟预览中不会更新程序。', disabled: '此安装尚未启用网页更新。', install_root_unavailable: '当前安装目录无法更新。',
  unsupported_platform: '当前系统暂不支持网页更新。', version_unknown: '无法确认当前版本，请先检查安装状态。',
  frontend_version_mismatch: '界面与服务版本不一致，请先检查安装状态。', dirty_worktree: '安装目录中有未保存到版本库的修改，暂不能更新。',
  running_version_mismatch: '运行版本与安装目录不一致，暂不能更新。', check_required: '请先检查更新。',
  check_stale: '版本信息已过期，请重新检查更新。', check_failed: '检查未成功，请重试。',
  worker_unavailable: '更新助手尚未运行。', job_active: '已有更新任务正在进行。', recovery_required: '请联系管理员检查更新状态。',
  up_to_date: '当前已是主分支的最新版本。', current_ahead: '当前版本领先主分支。',
  history_diverged: '当前版本与主分支存在不同修改，暂不能自动更新。', relationship_unknown: '尚未确认版本关系，请重新检查。',
  state_unavailable: '暂时无法读取更新状态。', target_changed: '可用版本已变化，请重新检查后确认。',
  github_unavailable: '暂时无法读取主分支，请稍后检查。', github_rate_limited: '版本检查过于频繁，请稍后重试。',
  github_invalid_response: '版本来源响应异常，请稍后检查。', compare_unavailable: '暂时无法比较版本，请稍后检查。',
  command_unavailable_or_timed_out: '所需工具不可用或执行超时，请联系管理员检查。',
  command_failed: '更新步骤执行失败，请联系管理员检查。',
  frontend_commit_mismatch: '新版界面构建未通过校验，原服务尚未切换。',
  required_lockfile_missing: '新版缺少构建所需文件，原服务尚未切换。',
  prepared_source_modified: '新版准备期间文件发生变化，更新已停止。',
  unsupported_source_entry: '新版包含暂不支持的文件类型，更新已停止。',
  installation_not_provisioned: '此安装尚未配置好更新助手，请联系管理员。',
  operator_configuration_required: '更新助手配置不完整，请联系管理员。',
  linux_root_helper_required: '更新助手需要管理员权限，请联系管理员启动。',
  unsupported_state_layout: '当前更新数据目录布局暂不支持，请联系管理员调整。',
  unsupported_current_layout: '当前安装布局暂不支持网页更新，请联系管理员。',
  unsupported_cloud_data_layout: '云端数据目录布局暂不支持，请联系管理员调整。',
  unsupported_local_data_path: '本地数据存放位置暂不支持更新，请联系管理员调整。',
  data_directory_missing: '所需数据目录不存在，请联系管理员检查。',
  linked_data_file: '数据目录中存在链接文件，暂不能自动备份。',
  unsupported_data_file: '数据目录中存在不支持的文件类型，暂不能自动备份。',
  browser_runtime_upgrade_requires_operator: '浏览器运行环境需要升级，请由管理员处理。',
  explicit_render_configuration_required: '图片生成设置不完整，请联系管理员检查。',
  explicit_render_runtime_required: '尚未配置图片生成所需的浏览器和字体，请联系管理员。',
  render_runtime_missing: '图片生成所需的浏览器或字体不可用，请联系管理员。',
  official_main_changed: '主分支在检查后已有变化，请重新检查并确认版本。',
  current_version_changed: '当前安装版本已变化，请重新读取更新状态。',
  current_not_ancestor: '当前版本无法直接升级到目标版本，请联系管理员检查。',
  already_current: '当前已是目标版本，请重新读取更新状态。',
  dirty_checkout: '版本目录中有未提交的修改，暂不能更新。',
  invalid_current_commit: '无法确认安装版本，请联系管理员检查。',
  invalid_release_manifest: '安装版本信息未通过校验，请联系管理员检查。',
  release_source_mismatch: '当前安装来源不符，暂不能自动更新。',
  service_did_not_stop: '服务未能停止，请联系管理员检查。',
  service_did_not_start: '服务未能启动，请联系管理员检查。',
  new_release_health_failed: '新版本未通过运行检查，请查看恢复状态。',
  data_changed_during_backup: '备份期间数据发生变化，请联系管理员检查。',
  backup_database_integrity_failed: '数据库备份未通过完整性检查，请联系管理员处理。',
  operator_recovery_required: '已有更新尚待恢复，请由管理员处理。',
  rollback_health_failed: '恢复原版本后仍未通过运行检查，请由管理员处理。',
  worker_interrupted: '更新助手曾中断，请联系管理员确认恢复状态。',
  update_operation_failed: '更新过程未能完成，请联系管理员检查。',
}
export const systemUpdateReason = code => REASONS[code] || (code ? '暂时无法更新，请重新检查状态。' : '')
export const updateIsRunning = snapshot => ACTIVE.has(snapshot?.job?.phase)
export const updateIsVerified = state => state.snapshot?.job?.phase === 'completed'
  && SHA.test(state.snapshot?.job?.target_sha || '') && state.snapshot.current?.sha === state.snapshot.job.target_sha && state.snapshot.current.frontend_sha === state.snapshot.job.target_sha
  && !state.readFailed && !state.connectionLost && !state.uncertain && !state.sessionEnded
export const canApplySystemUpdate = state => !state.operation && !state.readFailed && !state.checkFailed && !state.uncertain
  && !state.connectionLost && !state.timedOut && !state.sessionEnded && state.snapshot?.can_apply === true
  && state.snapshot.worker_available === true && state.snapshot.stale !== true && !state.snapshot.check_error
  && state.snapshot.relation === 'ahead' && SHA.test(state.snapshot.current?.sha || '') && SHA.test(state.snapshot.latest?.sha || '')
  && state.snapshot.current.sha !== state.snapshot.latest.sha && !updateIsRunning(state.snapshot)
  && state.snapshot.job?.phase !== 'recovery_required'
  && !(state.snapshot.job?.phase === 'completed' && !updateIsVerified(state))

export function systemUpdateStatus(state) {
  if (state.accessError) return state.accessError
  if (state.sessionEnded) return '网站会话已变化，请关闭此窗口后重新登录。'
  if (state.timedOut) return '等待时间较长，请手动检查更新状态。'
  if (state.connectionLost) return '服务暂时断开，正在等待服务恢复…'
  if (state.uncertain) return '正在确认更新请求是否已接收…'
  if (state.operation === 'checking') return '正在检查主分支的最新版本…'
  if (state.operation === 'reading' && !state.snapshot) return '正在读取更新状态…'
  if (state.readFailed) return '更新状态暂时未知，请重新读取。'
  const snapshot = state.snapshot
  if (!snapshot) return '尚未读取版本信息。'
  if (snapshot.job?.phase === 'completed') {
    if (updateIsVerified(state) && snapshot.relation === 'ahead' && snapshot.latest?.sha !== snapshot.job.target_sha) return '发现主分支的新版本。'
    return updateIsVerified(state) ? '更新完成，新版本已开始运行。' : '更新任务已结束，正在核对运行版本…'
  }
  if (snapshot.job && UPDATE_PHASES[snapshot.job.phase]) return UPDATE_PHASES[snapshot.job.phase]
  if (state.checkFailed || snapshot.check_error || snapshot.stale) return snapshot.checked_at
    ? '版本信息已过期，请重新检查。' : '尚未取得版本信息，请检查更新。'
  return ({ ahead: '发现主分支的新版本。', behind: '当前版本领先主分支。', up_to_date: '当前已是主分支的最新版本。',
    diverged: '当前版本与主分支存在不同修改。', unknown: '尚未确认版本关系。' })[snapshot.relation]
}

function validStatus(value) {
  if (!value || value.repository !== 'miyako-md/game-manage' || value.branch !== 'main' || !value.current
    || !RELATIONS.has(value.relation) || (value.current.sha != null && !SHA.test(value.current.sha))
    || (value.latest != null && !SHA.test(value.latest.sha || ''))
    || (value.job != null && (!value.job.job_id || !UPDATE_PHASES[value.job.phase] || !SHA.test(value.job.target_sha || '')))) {
    throw new Error('更新状态响应异常，请重新读取。')
  }
  return value
}

/** One controller per opened dialog. A lost POST response is resolved by reads;
 * no mutation is ever retried automatically, including across service restarts. */
export function createSystemUpdateController({
  api = { get: getSystemUpdate, check: checkSystemUpdate, apply: applySystemUpdate },
  now = Date.now, setTimer = setTimeout, clearTimer = clearTimeout, subscribe = subscribeSessionInvalidation,
} = {}) {
  const state = reactive({ snapshot: null, operation: '', error: '', readFailed: false, checkFailed: false,
    connectionLost: false, uncertain: false, timedOut: false, sessionEnded: false, accessError: '' })
  let disposed = false, generation = 0, pollTimer = null, requestTimer = null, request = null
  let trackingSince = null, pendingApply = null, pendingCheckAt = undefined
  const clearPoll = () => { if (pollTimer != null) clearTimer(pollTimer); pollTimer = null }
  const tracks = () => state.uncertain || state.connectionLost || updateIsRunning(state.snapshot)
    || (state.snapshot?.job?.phase === 'completed' && !updateIsVerified(state))
  function schedule() {
    clearPoll()
    if (disposed || state.sessionEnded || state.operation || state.timedOut || !tracks()) return
    trackingSince ??= now()
    if (now() - trackingSince >= MAX_WAIT) { state.timedOut = true; return }
    pollTimer = setTimer(() => { pollTimer = null; read() }, state.connectionLost ? 4000 : 2000)
  }
  function receive(value) {
    const snapshot = validStatus(value)
    state.snapshot = snapshot
    state.readFailed = false; state.connectionLost = false
    if (pendingCheckAt !== undefined && snapshot.checked_at !== pendingCheckAt && !snapshot.check_error && !snapshot.stale) {
      state.checkFailed = false; pendingCheckAt = undefined
    }
    if (pendingApply && snapshot.job?.target_sha === pendingApply.target_sha && snapshot.job.previous_sha === pendingApply.expected_sha) {
      state.uncertain = false; pendingApply = null
    }
    if (!state.checkFailed && !state.uncertain) state.error = ''
    if (!tracks()) trackingSince = null
  }
  async function call(action, timeout) {
    request = new AbortController()
    const own = request
    requestTimer = setTimer(() => own.abort(), timeout)
    try { return await action({ signal: own.signal }) }
    finally {
      if (requestTimer != null) clearTimer(requestTimer)
      requestTimer = null
      if (request === own) request = null
    }
  }
  async function read() {
    if (disposed || state.sessionEnded || state.operation) return
    clearPoll()
    const version = generation
    state.operation = 'reading'
    try {
      const value = await call(api.get, 15000)
      if (disposed || version !== generation) return
      receive(value)
    } catch (error) {
      if (disposed || version !== generation) return
      if (error.status === 401 || error.status === 403) {
        endAccess(error.status === 403 ? '管理员权限已失效，无法查看或执行系统更新。' : '网站会话已失效，请重新登录。')
        return
      }
      state.readFailed = true
      state.connectionLost = true
      state.error = '暂时无法读取更新状态。'
    } finally {
      if (!disposed && version === generation) { state.operation = ''; schedule() }
    }
  }
  async function check() {
    if (disposed || state.sessionEnded || state.operation || state.uncertain || updateIsRunning(state.snapshot)) return
    clearPoll()
    const version = generation
    state.operation = 'checking'; state.error = ''; state.timedOut = false; trackingSince = null
    pendingCheckAt = state.snapshot?.checked_at ?? null
    let confirm = false
    try {
      const value = await call(api.check, 60000)
      if (disposed || version !== generation) return
      receive(value)
      state.checkFailed = Boolean(value.check_error || value.stale)
      pendingCheckAt = undefined
      if (state.checkFailed) state.error = systemUpdateReason(value.check_error) || '检查未成功，请重试。'
    } catch (error) {
      if (disposed || version !== generation) return
      state.checkFailed = true
      state.error = systemUpdateReason(error.code) || '检查未成功，请稍后重试。'
      confirm = !error.status || error.status >= 500
    } finally {
      if (!disposed && version === generation) {
        state.operation = ''
        if (confirm) await read()
        else schedule()
      }
    }
  }
  async function apply(target) {
    if (disposed || !canApplySystemUpdate(state)) return
    if (target !== state.snapshot.latest.sha) { state.error = REASONS.target_changed; return }
    clearPoll()
    const version = generation
    pendingApply = { expected_sha: state.snapshot.current.sha, target_sha: target }
    state.uncertain = true; state.operation = 'applying'; state.error = ''; trackingSince = now()
    let confirm = false
    try {
      const value = await call(options => api.apply(pendingApply, options), 15000)
      if (disposed || version !== generation) return
      receive(value)
      confirm = state.uncertain
    } catch (error) {
      if (disposed || version !== generation) return
      if (error.status >= 400 && error.status < 500) { pendingApply = null; state.uncertain = false }
      state.error = systemUpdateReason(error.code) || '更新请求尚未确认，正在重新读取状态。'
      state.readFailed = true
      confirm = true
    } finally {
      if (!disposed && version === generation) {
        state.operation = ''
        if (confirm) await read()
        else schedule()
      }
    }
  }
  function endAccess(accessError = '') {
    generation++; clearPoll(); request?.abort()
    if (requestTimer != null) clearTimer(requestTimer)
    requestTimer = null; request = null; pendingApply = null; pendingCheckAt = undefined; trackingSince = null
    Object.assign(state, { snapshot: null, operation: '', error: '', readFailed: false, checkFailed: false,
      uncertain: false, connectionLost: false, timedOut: false, sessionEnded: true, accessError })
  }
  const unsubscribe = subscribe(() => endAccess())
  return { state, start: read, read, check, apply,
    retryStatus() { if (!disposed && !state.sessionEnded) { state.timedOut = false; trackingSince = now(); return read() } },
    destroy() {
      if (disposed) return
      disposed = true; generation++; clearPoll(); request?.abort()
      if (requestTimer != null) clearTimer(requestTimer)
      requestTimer = null; request = null; unsubscribe()
    },
  }
}
