<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { session } from '../session'
import { date, money, shortId, validAmount } from '../format'

const props = defineProps({ id: { type: String, required: true } })

// Only the admin holds REVERSE (§8.15). The token carries the role, not the permissions,
// so the button follows the role; the API still checks the permission
const canReverse = computed(() => session.role === 'ADMIN')

const account = ref(null)
const error = ref('')
const loading = ref(true)

// Other accounts to choose as transfer destination: every account, or only the client's own.
// Any other destination is entered by its id
const OTHER = 'other'
const destinations = ref([])

const operation = ref('deposit')
const amount = ref('')
const destination = ref('')
const destinationId = ref('')
const formError = ref('')
const notice = ref('')
const busy = ref(false)

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

function choose(name) {
  operation.value = name
  formError.value = ''
  notice.value = ''
}

async function submit() {
  formError.value = ''
  notice.value = ''
  const value = amount.value.trim()
  if (!validAmount(value)) {
    formError.value = 'Amount must be greater than zero with at most 2 decimals'
    return
  }
  const destinationAccountId = destination.value === OTHER ? destinationId.value.trim() : destination.value
  if (operation.value === 'transfer' && !destinationAccountId) {
    formError.value = 'Choose a destination account'
    return
  }

  busy.value = true
  try {
    let result
    if (operation.value === 'deposit') {
      result = await api.deposit(props.id, value)
    } else if (operation.value === 'withdrawal') {
      result = await api.withdrawal(props.id, value)
    } else {
      result = await api.transfer(props.id, destinationAccountId, value)
    }
    notice.value = `${result.type} of ${money(result.amount)} applied. New balance: ${money(result.balance)}`
    amount.value = ''
    await load()
  } catch (failure) {
    formError.value = failure.message
  } finally {
    busy.value = false
  }
}

async function reverse(movement) {
  if (!confirm(`Reverse the ${movement.type} of ${money(movement.amount)}? This applies to every account it touched.`)) {
    return
  }
  formError.value = ''
  notice.value = ''
  try {
    const result = await api.reverse(movement.transaction_id)
    notice.value = `${result.original_type} of ${money(result.amount)} reversed`
    await load()
  } catch (failure) {
    formError.value = failure.message
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
        <section class="card">
          <h2>New operation</h2>
          <div class="tabs">
            <button :class="{ active: operation === 'deposit' }" @click="choose('deposit')">Deposit</button>
            <button :class="{ active: operation === 'withdrawal' }" @click="choose('withdrawal')">Withdrawal</button>
            <button :class="{ active: operation === 'transfer' }" @click="choose('transfer')">Transfer</button>
          </div>
          <form @submit.prevent="submit">
            <p v-if="formError" class="alert error">{{ formError }}</p>
            <p v-if="notice" class="alert success">{{ notice }}</p>
            <label v-if="operation === 'transfer'">Destination account
              <select v-model="destination" required>
                <option value="" disabled>Choose an account</option>
                <option v-for="other in destinations" :key="other.id" :value="other.id">
                  {{ other.alias }} · {{ other.holder }} ({{ other.account_class }})
                </option>
                <option :value="OTHER">Another account (enter its id)</option>
              </select>
            </label>
            <label v-if="operation === 'transfer' && destination === OTHER">Destination account id
              <input v-model="destinationId" class="mono" placeholder="00000000-0000-0000-0000-000000000000" required>
            </label>
            <label>Amount (MXN)
              <input v-model="amount" class="mono" inputmode="decimal" placeholder="0.00" required>
            </label>
            <button :disabled="busy">{{ busy ? 'Applying…' : 'Apply' }}</button>
          </form>
        </section>

        <section class="card history">
          <h2>Movements</h2>
          <p v-if="!movements.length" class="muted">This account has no movements yet.</p>
          <div v-else class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Type</th>
                  <th>Transaction</th>
                  <th class="num">Amount</th>
                  <th class="num">Balance</th>
                  <th v-if="canReverse"></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="movement in movements" :key="movement.movement_id">
                  <td class="muted">{{ date(movement.created_at) }}</td>
                  <td>{{ movement.type }}</td>
                  <td class="mono muted" :title="movement.transaction_id">{{ shortId(movement.transaction_id) }}</td>
                  <td class="num mono" :class="movement.entry_type === 'CREDIT' ? 'credit' : 'debit'">
                    {{ movement.entry_type === 'CREDIT' ? '+' : '−' }}{{ money(movement.amount) }}
                  </td>
                  <td class="num mono">{{ money(movement.balance) }}</td>
                  <td v-if="canReverse" class="num">
                    <button v-if="movement.type !== 'REVERSAL'" class="danger" @click="reverse(movement)">Reverse</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </template>
  </main>
</template>

<style scoped>
.back { display: inline-block; font-size: .875rem; margin-bottom: 16px; }
.page-head h1 { margin-top: 6px; }
.id { font-size: .8rem; margin-top: 2px; word-break: break-all; }
.balance { display: grid; text-align: right; }
.balance span { font-size: .8rem; }
.balance strong { font-size: 1.8rem; font-weight: 500; }
.layout { display: grid; grid-template-columns: 320px 1fr; gap: 20px; align-items: start; }
.history { min-width: 0; }
@media (max-width: 860px) {
  .layout { grid-template-columns: 1fr; }
  .balance { text-align: left; }
}
</style>
