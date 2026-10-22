<script setup>
import { reactive, ref, watch } from 'vue'
import { api } from '../api'
import TabSwitch from './TabSwitch.vue'

// Opens a client with their first VOSTRO account, another VOSTRO or a NOSTRO account.
// Emits opened with the new account so the view decides where to go next
const emit = defineEmits(['opened'])

const kinds = { client: 'New client', vostro: 'VOSTRO', nostro: 'NOSTRO' }
const hints = {
  client: 'Creates the CLIENT user and their first VOSTRO account (§8.3).',
  vostro: 'Another VOSTRO account for an existing client (§8.4).',
  nostro: 'An account of the bank itself (§8.13).'
}

const kind = ref('client')
const form = reactive({ email: '', password: '', name: '', alias: '' })
const error = ref('')
const busy = ref(false)

watch(kind, () => {
  error.value = ''
})

async function submit() {
  error.value = ''
  busy.value = true
  try {
    let account
    if (kind.value === 'client') {
      account = await api.openClient({ email: form.email, password: form.password, name: form.name, alias: form.alias })
    } else if (kind.value === 'vostro') {
      account = await api.openVostro({ email: form.email, alias: form.alias })
    } else {
      account = await api.openNostro({ alias: form.alias })
    }
    emit('opened', account)
  } catch (failure) {
    error.value = failure.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div>
    <TabSwitch v-model="kind" :options="kinds" />
    <p class="muted hint">{{ hints[kind] }}</p>
    <form @submit.prevent="submit">
      <p v-if="error" class="alert error">{{ error }}</p>
      <label v-if="kind !== 'nostro'">Client email
        <input v-model="form.email" type="email" required>
      </label>
      <template v-if="kind === 'client'">
        <label>Client name
          <input v-model="form.name" required>
        </label>
        <label>Temporary password
          <input v-model="form.password" type="password" autocomplete="new-password" required>
        </label>
      </template>
      <label>Alias
        <input v-model="form.alias" required>
      </label>
      <button :disabled="busy">{{ busy ? 'Opening…' : 'Open account' }}</button>
    </form>
  </div>
</template>

<style scoped>
.hint { font-size: .875rem; margin-bottom: 16px; }
</style>
