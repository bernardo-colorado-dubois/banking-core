<script setup>
import { ref } from 'vue'
import { api } from '../api'
import { session } from '../session'
import BankLogo from './BankLogo.vue'

// Logs in and starts the session. Emits logged-in with the API result so the view
// decides where to go next
defineProps({
  // The previous session ended with a 401; the notice gives way to any new error
  expired: { type: Boolean, default: false },
})
const emit = defineEmits(['logged-in'])

const email = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

async function submit() {
  error.value = ''
  busy.value = true
  try {
    const result = await api.login(email.value.trim(), password.value)
    session.start(result.token, result.must_change_password)
    emit('logged-in', result)
  } catch (failure) {
    error.value = failure.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="card box">
    <BankLogo :size="44" class="logo" />
    <h1>Banking core</h1>
    <p class="muted lead">Log in to manage accounts and movements.</p>
    <form @submit.prevent="submit">
      <p v-if="expired && !error" class="alert error">Your session expired. Log in again.</p>
      <p v-if="error" class="alert error">{{ error }}</p>
      <label>Email
        <input v-model="email" type="email" autocomplete="username" required>
      </label>
      <label>Password
        <input v-model="password" type="password" autocomplete="current-password" required>
      </label>
      <button :disabled="busy">{{ busy ? 'Logging in…' : 'Log in' }}</button>
    </form>
  </div>
</template>

<style scoped>
.box { width: 100%; max-width: 380px; }
.logo { color: var(--accent); margin-bottom: 12px; }
.lead { margin: 4px 0 24px; font-size: .9rem; }
</style>
