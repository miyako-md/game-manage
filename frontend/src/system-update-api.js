import { requestJson } from './http-client.js'

const path = '/api/system/update'
export const getSystemUpdate = options => requestJson(path, options)
export const checkSystemUpdate = options => requestJson(`${path}/check`, { ...options, method: 'POST', body: {} })
export const applySystemUpdate = ({ expected_sha, target_sha }, options) => requestJson(`${path}/apply`, {
  ...options, method: 'POST', body: { expected_sha, target_sha },
})
