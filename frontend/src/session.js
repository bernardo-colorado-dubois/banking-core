import { reactive } from 'vue'

// The token lives in sessionStorage: it survives a reload but dies with the tab.
// There is no refresh token, so when it expires the user logs in again.
const STORAGE_KEY = 'banking-core-session'

function claims(token) {
  const payload = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
  return JSON.parse(atob(payload))
}

function restore() {
  try {
    const stored = JSON.parse(sessionStorage.getItem(STORAGE_KEY))
    if (stored && claims(stored.token).exp * 1000 > Date.now()) {
      return stored
    }
  } catch {
    // Missing or unreadable storage: start logged out
  }
  return { token: null, mustChangePassword: false }
}

function persist() {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
      token: session.token,
      mustChangePassword: session.mustChangePassword
    }))
  } catch {
    // The session still works in memory
  }
}

export const session = reactive({
  ...restore(),

  get userId() {
    return this.token ? claims(this.token).sub : null
  },

  get role() {
    return this.token ? claims(this.token).role : null
  },

  start(token, mustChangePassword) {
    this.token = token
    this.mustChangePassword = mustChangePassword
    persist()
  },

  passwordChanged() {
    this.mustChangePassword = false
    persist()
  },

  end() {
    this.token = null
    this.mustChangePassword = false
    try {
      sessionStorage.removeItem(STORAGE_KEY)
    } catch {
      // Nothing stored
    }
  }
})
