import { reactive } from 'vue'

export const session = reactive({
  ready: false, error: '', user: null, registration: false, anonymous: false, mail_available: false,
  source_url: null,
})

export async function api(path, { method = 'GET', body, signal } = {}) {
  const headers = { Accept: 'application/json' }
  if (method !== 'GET') headers['X-TFWatch-Request'] = '1'
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  let response
  try {
    response = await fetch('/api' + path, {
      method, signal, headers, body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch (error) {
    if (error.name === 'AbortError') throw error
    throw new Error('暂时无法连接服务器')
  }
  if (response.status === 204) return null
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const error = new Error(typeof data?.detail === 'string' ? data.detail : '请求失败，请稍后重试')
    error.status = response.status
    throw error
  }
  return data
}

export async function refreshSession() {
  session.error = ''
  try {
    Object.assign(session, await api('/session'))
  } catch (error) {
    session.error = error.message
  } finally {
    session.ready = true
  }
}

