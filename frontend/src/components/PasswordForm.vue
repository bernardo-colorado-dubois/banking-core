<script setup>
import { ref } from 'vue'
import { api } from '../api'
import { session } from '../session'

// Changes the password and clears the pending flag of the session. Emits changed so the
// view decides where to go next
const emit = defineEmits(['changed'])

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
    emit('changed')
  } catch (failure) {
    error.value = failure.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
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
</template>
