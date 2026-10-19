<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { session } from '../session'

const route = useRoute()
const router = useRouter()
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
    router.push(result.must_change_password ? { name: 'password' } : { name: 'accounts' })
  } catch (failure) {
    error.value = failure.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="center">
    <div class="card box">
      <h1>Banking core</h1>
      <p class="muted lead">Log in to manage accounts and movements.</p>
      <form @submit.prevent="submit">
        <p v-if="route.query.expired && !error" class="alert error">Your session expired. Log in again.</p>
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
  </main>
</template>

<style scoped>
.center { min-height: 100vh; display: grid; place-items: center; padding: 16px; }
.box { width: 100%; max-width: 380px; }
.lead { margin: 4px 0 24px; font-size: .9rem; }
</style>
