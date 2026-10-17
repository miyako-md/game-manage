import { execFileSync } from 'node:child_process'

export function buildVersion(root, env = process.env, readCommit = () => execFileSync('git', ['rev-parse', 'HEAD'], {
  cwd: root, encoding: 'utf8', timeout: 3000, stdio: ['ignore', 'pipe', 'ignore'],
})) {
  let commit = null
  if (env.GA_BUILD_COMMIT !== undefined) {
    if (!/^[a-f0-9]{40}$/.test(env.GA_BUILD_COMMIT)) throw new Error('GA_BUILD_COMMIT must be a full commit SHA')
    commit = env.GA_BUILD_COMMIT
  } else {
    try {
      const value = readCommit().trim()
      if (/^[a-f0-9]{40}$/.test(value)) commit = value
    } catch { /* An unpacked source archive has no Git identity. Keep it unknown. */ }
  }
  return { schema: 1, source: 'miyako-md/game-manage', commit, mode: env.VITE_SERVICE_MODE === 'cloud' ? 'cloud' : 'local' }
}
