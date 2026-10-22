<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { session } from '../session'
import { money } from '../format'
import MovementsTable from '../components/MovementsTable.vue'
import OperationPanel from '../components/OperationPanel.vue'

const props = defineProps({ id: { type: String, required: true } })

// Only the admin holds REVERSE (§8.15). The token carries the role, not the permissions,
// so the button follows the role; the API still checks the permission
const canReverse = computed(() => session.role === 'ADMIN')

const account = ref(null)
const error = ref('')
const loading = ref(true)

// Other accounts to choose as transfer destination: every account, or only the client's own
const destinations = ref([])

const reverseError = ref('')
const reverseNotice = ref('')

const balance = computed(() => {
  const movements = account.value?.movements ?? []
  return movements.length ? movements[movements.length - 1].balance : '0.00'
})

// The API returns the history from oldest to newest; the table shows the newest first
const movements = computed(() => [...(account.value?.movements ?? [])].reverse())

async function load() {
  loading.value = true
  error.value = ''
  try {
    account.value = await api.history(props.id)
  } catch (failure) {
    error.value = failure.message
  } finally {
    loading.value = false
  }
}

async function loadDestinations() {
  try {
    destinations.value = (await api.accounts()).accounts.filter((other) => other.id !== props.id)
  } catch {
    destinations.value = []
  }
}

onMounted(() => {
  load()
  loadDestinations()
})
watch(() => props.id, () => {
  load()
  loadDestinations()
})

async function reverse(movement) {
  if (!confirm(`Reverse the ${movement.type} of ${money(movement.amount)}? This applies to every account it touched.`)) {
    return
  }
  reverseError.value = ''
  reverseNotice.value = ''
  try {
    const result = await api.reverse(movement.transaction_id)
    reverseNotice.value = `${result.original_type} of ${money(result.amount)} reversed`
    await load()
  } catch (failure) {
    reverseError.value = failure.message
  }
}
</script>

<template>
  <main class="page">
    <RouterLink to="/" class="back">← Accounts</RouterLink>

    <p v-if="loading && !account" class="muted">Loading…</p>
    <p v-else-if="error" class="alert error">{{ error }}</p>

    <template v-else-if="account">
      <div class="page-head">
        <div>
          <span class="badge">{{ account.account_class }}</span>
          <h1>{{ account.alias }}</h1>
          <p class="muted mono id">{{ account.account_id }}</p>
        </div>
        <div class="balance">
          <span class="muted">Balance</span>
          <strong class="mono">{{ money(balance) }}</strong>
        </div>
      </div>

      <div class="layout">
        <section class="card operations">
          <h2>New operation</h2>
          <OperationPanel :key="id" :account-id="id" :destinations="destinations" @applied="load" />
        </section>

        <section class="card history">
          <h2>Movements</h2>
          <p v-if="reverseError" class="alert error">{{ reverseError }}</p>
          <p v-if="reverseNotice" class="alert success">{{ reverseNotice }}</p>
          <p v-if="!movements.length" class="muted">This account has no movements yet.</p>
          <MovementsTable v-else :movements="movements" :can-reverse="canReverse" @reverse="reverse" />
        </section>
      </div>
    </template>
  </main>
</template>

<style scoped>
.page-head h1 { margin-top: 6px; }
.id { font-size: .8rem; margin-top: 2px; word-break: break-all; }
.balance { display: grid; text-align: right; }
.balance span { font-size: .8rem; }
.balance strong { font-size: 1.8rem; font-weight: 500; }
.layout { display: grid; grid-template-columns: 300px 1fr; gap: 16px; align-items: start; }
.operations, .history { min-width: 0; padding: 20px 16px; }
.history .alert { margin-bottom: 12px; }
@media (max-width: 860px) {
  .layout { grid-template-columns: 1fr; }
  .balance { text-align: left; }
}
</style>
