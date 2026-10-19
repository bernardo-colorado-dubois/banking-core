import { session } from './session'
import router from './router'

// Every call goes through the /api proxy of the dev server (vite.config.js)
async function request(method, path, body) {
  const headers = {}
  if (session.token) {
    headers.Authorization = `Bearer ${session.token}`
  }
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
  }

  const response = await fetch(`/api${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body)
  })
  const data = await response.json().catch(() => ({}))

  // An expired or rejected token sends the user back to the login
  if (response.status === 401 && session.token) {
    session.end()
    router.push({ name: 'login', query: { expired: '1' } })
  }
  if (!response.ok) {
    const error = new Error(data.error || `Request failed with status ${response.status}`)
    error.status = response.status
    throw error
  }
  return data
}

export const api = {
  login: (email, password) => request('POST', '/user/login', { email, password }),
  changePassword: (currentPassword, newPassword) =>
    request('POST', '/user/password', { current_password: currentPassword, new_password: newPassword }),
  profile: (userId) => request('GET', `/user/${userId}`),

  accounts: () => request('GET', '/account/'),
  history: (accountId) => request('GET', `/account/${accountId}/balance`),
  openClient: (data) => request('POST', '/account/client', data),
  openVostro: (data) => request('POST', '/account/vostro', data),
  openNostro: (data) => request('POST', '/account/nostro', data),

  deposit: (accountId, amount) => request('POST', `/account/${accountId}/deposit`, { amount }),
  withdrawal: (accountId, amount) => request('POST', `/account/${accountId}/withdrawal`, { amount }),
  transfer: (accountId, destinationAccountId, amount) =>
    request('POST', `/account/${accountId}/transfer`, { destination_account_id: destinationAccountId, amount }),
  reverse: (transactionId) => request('POST', `/account/transaction/${transactionId}/reversal`)
}
