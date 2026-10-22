<script setup>
import { ref } from 'vue'
import { api } from '../api'
import { session } from '../session'

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
</template>
