import { requestResponse } from './http-client.js'
const ROOT='/api/admin/guides'
const messages={guide_check_cooldown:'立即检查冷却中，请稍后再试',scheduler_unavailable:'后台调度暂不可用，请稍后重试'}
async function request(path,method,signal) {
  const timeout=AbortSignal.timeout(30000)
  let response
  try {
    response=await requestResponse(ROOT+path,{method,signal:signal?AbortSignal.any([signal,timeout]):timeout})
  } catch(error) {
    if(timeout.aborted&&!signal?.aborted) throw new Error('请求超时，请稍后重试')
    throw error
  }
  const data=await response.json().catch(()=>null)
  if(!response.ok) {
    // Machine codes get fixed text; retry_after (seconds) drives the button cooldown.
    const detail=typeof data?.detail==='string'?data.detail.slice(0,64):''
    const error=new Error(messages[detail]||'攻略更新状态暂不可用，请稍后重试')
    Object.assign(error,{status:response.status,detail,retryAfter:Number(data?.retry_after||response.headers?.get?.('Retry-After'))||0})
    throw error
  }
  if(!data||typeof data!=='object'||Array.isArray(data)) throw new Error('攻略更新状态响应异常')
  return data
}
export async function getCloudGuideStatus(signal) {
  const value=await request('','GET',signal)
  if(!value.job||typeof value.job!=='object'||!value.wuthering_waves||!value.nte) throw new Error('攻略更新状态响应异常')
  return value
}
export const checkCloudGuides=signal=>request('/check','POST',signal)
// Extract one pending WuWa post now (the same administrator route the role guide page uses).
export async function extractCloudGuide(item,signal) {
  const timeout=AbortSignal.timeout(90000)
  const body=JSON.stringify({character_id:String(item.character_id),name:item.name,attribute:item.attribute||'',post_id:String(item.post_id)})
  let response
  try {
    response=await requestResponse('/api/admin/wuwa/guides/updates/extract',{method:'POST',headers:{'Content-Type':'application/json','X-Game-Assistant':'1'},body,signal:signal?AbortSignal.any([signal,timeout]):timeout})
  } catch(error) {
    if(timeout.aborted&&!signal?.aborted) throw new Error('提炼超时，请稍后在状态里查看结果')
    throw error
  }
  const data=await response.json().catch(()=>null)
  if(!response.ok) throw new Error(typeof data?.detail==='string'&&data.detail.length<=64?data.detail:'提炼失败，请稍后重试')
  return data
}
