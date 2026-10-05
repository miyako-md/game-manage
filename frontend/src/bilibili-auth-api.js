const ROOT = '/api/auth/bilibili-source/login'
export class BilibiliAuthError extends Error {
  constructor(message, { status=0, errorCode='', state='', retryAfter=0, timedOut=false }={}) {
    super(message); this.name='BilibiliAuthError'
    Object.assign(this,{status,errorCode,state,retryAfter,timedOut})
  }
}
async function request(path, method='GET', body, signal) {
  const headers={Accept:'application/json'}
  if(method!=='GET') headers['X-Game-Assistant']='1'
  if(body!==undefined) headers['Content-Type']='application/json'
  const timeout=AbortSignal.timeout(75000)
  let response
  try {
    response=await fetch(ROOT+path,{method,headers,credentials:'same-origin',
      ...(body!==undefined?{body:JSON.stringify(body)}:{}), signal:signal?AbortSignal.any([signal,timeout]):timeout})
  } catch {
    if(signal?.aborted) throw new DOMException('已取消','AbortError')
    throw new BilibiliAuthError(timeout.aborted?'请求超时，请检查会话状态后重试':'无法连接B站登录服务，请稍后重试',{timedOut:timeout.aborted})
  }
  let data
  try { data=await response.json() } catch { /* Never display HTML or upstream diagnostics. */ }
  if(!response.ok) {
    const retry=Number(response.headers.get('Retry-After')||data?.retry_after)
    throw new BilibiliAuthError(typeof data?.detail==='string'?data.detail.slice(0,256):'B站登录暂时不可用，请稍后重试',{
      status:response.status,errorCode:typeof data?.error_code==='string'?data.error_code:'',
      state:typeof data?.state==='string'?data.state:'',retryAfter:Number.isFinite(retry)&&retry>0?Math.ceil(retry):0})
  }
  if(!data||typeof data!=='object'||Array.isArray(data)) throw new BilibiliAuthError('登录服务响应异常，请重试')
  return data
}
const session=sid=>`/sessions/${encodeURIComponent(sid)}`
export const getBilibiliAuthStatus=signal=>request('/status','GET',undefined,signal)
export const createBilibiliSession=(mode,signal)=>request('/sessions','POST',{mode},signal)
export const getBilibiliSession=(sid,signal)=>request(session(sid),'GET',undefined,signal)
export const cancelBilibiliSession=(sid,signal)=>request(session(sid),'DELETE',undefined,signal)
export const createBilibiliCaptcha=(sid,signal)=>request(session(sid)+'/captcha','POST',undefined,signal)
export const submitBilibiliPassword=(sid,body,signal)=>request(session(sid)+'/password','POST',body,signal)
export const sendBilibiliSms=(sid,body,signal)=>request(session(sid)+'/sms/send','POST',body,signal)
export const submitBilibiliSms=(sid,code,signal)=>request(session(sid)+'/sms/submit','POST',{code},signal)
export const pollBilibiliQr=(sid,signal)=>request(session(sid)+'/qr/poll','POST',undefined,signal)
export const importBilibiliCookie=(sid,body,signal)=>request(session(sid)+'/cookie','POST',body,signal)
export const commitBilibiliSession=(sid,signal)=>request(session(sid)+'/commit','POST',undefined,signal)
