<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'

const router = useRouter()
const kind = ref('client')
const form = reactive({ email: '', password: '', name: '', alias: '' })
const error = ref('')
const busy = ref(false)

const kinds = {
  client: { label: 'New client', hint: 'Creates the CLIENT user and their first VOSTRO account (§8.3).' },
  vostro: { label: 'VOSTRO', hint: 'Another VOSTRO account for an existing client (§8.4).' },
  nostro: { label: 'NOSTRO', hint: 'An account of the bank itself (§8.13).' }
}

function choose(name) {
  kind.value = name
  error.value = ''
}

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
    router.push({ name: 'account', params: { id: account.id } })
  } catch (failure) {
    error.value = failure.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="page narrow">
    <RouterLink to="/" class="back">← Accounts</RouterLink>
    <div class="card">
      <h1>Open account</h1>
      <div class="tabs">
        <button v-for="(item, name) in kinds" :key="name" :class="{ active: kind === name }" @click="choose(name)">
          {{ item.label }}
        </button>
      </div>
      <p class="muted hint">{{ kinds[kind].hint }}</p>
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
  </main>
</template>

<style scoped>
.narrow { max-width: 520px; }
.back { display: inline-block; font-size: .875rem; margin-bottom: 16px; }
h1 { margin-bottom: 20px; }
.hint { font-size: .875rem; margin-bottom: 16px; }
</style>
