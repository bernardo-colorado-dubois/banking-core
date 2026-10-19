<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { session } from '../session'

const router = useRouter()
const currentPassword = ref('')
const newPassword = ref('')
const confirmation = ref('')
const error = ref('')
const busy = ref(false)

async function submit() {
  error.value = ''
  if (newPassword.value !== confirmation.value) {
    error.value = 'The new passwords do not match'
    return
  }
  busy.value = true
  try {
    await api.changePassword(currentPassword.value, newPassword.value)
    session.passwordChanged()
    router.push({ name: 'accounts' })
  } catch (failure) {
    error.value = failure.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="page narrow">
    <div class="card">
      <h1>Change password</h1>
      <p v-if="session.mustChangePassword" class="muted lead">You must set a new password before continuing.</p>
      <form @submit.prevent="submit">
        <p v-if="error" class="alert error">{{ error }}</p>
        <label>Current password
          <input v-model="currentPassword" type="password" autocomplete="current-password" required>
        </label>
        <label>New password
          <input v-model="newPassword" type="password" autocomplete="new-password" required>
        </label>
        <label>Confirm new password
          <input v-model="confirmation" type="password" autocomplete="new-password" required>
        </label>
        <button :disabled="busy">{{ busy ? 'Saving…' : 'Change password' }}</button>
      </form>
    </div>
  </main>
</template>

<style scoped>
.narrow { max-width: 440px; }
.lead { margin: 4px 0 20px; font-size: .9rem; }
h1 { margin-bottom: 16px; }
</style>
