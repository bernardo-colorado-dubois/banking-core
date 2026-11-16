<script setup>
import { ref, watch } from 'vue'
import { api } from '../api'
import { money, validAmount } from '../format'
import TabSwitch from './TabSwitch.vue'

// Deposit, withdrawal and transfer from accountId (§8.5 to §8.12). Emits applied with the
// API result so the view reloads the history
const props = defineProps({
  accountId: { type: String, required: true },
  // Accounts to choose as transfer destination; any other one is entered by its id
  destinations: { type: Array, default: () => [] },
})
const emit = defineEmits(['applied'])

const operations = { deposit: 'Deposit', withdrawal: 'Withdrawal', transfer: 'Transfer' }
const OTHER = 'other'

const operation = ref('deposit')
const amount = ref('')
const destination = ref('')
const destinationId = ref('')
const error = ref('')
const notice = ref('')
const busy = ref(false)

watch(operation, () => {
  error.value = ''
  notice.value = ''
})

async function submit() {
  error.value = ''
  notice.value = ''
  const value = amount.value.trim()
  if (!validAmount(value)) {
    error.value = 'Amount must be greater than zero with at most 2 decimals'
    return
  }
  const destinationAccountId = destination.value === OTHER ? destinationId.value.trim() : destination.value
  if (operation.value === 'transfer' && !destinationAccountId) {
    error.value = 'Choose a destination account'
    return
  }

  busy.value = true
  try {
    let result
    if (operation.value === 'deposit') {
      result = await api.deposit(props.accountId, value)
    } else if (operation.value === 'withdrawal') {
      result = await api.withdrawal(props.accountId, value)
    } else {
      result = await api.transfer(props.accountId, destinationAccountId, value)
    }
    notice.value = `${result.type} of ${money(result.amount)} applied. New balance: ${money(result.balance)}`
    amount.value = ''
    emit('applied', result)
  } catch (failure) {
    error.value = failure.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="operation-panel">
    <TabSwitch v-model="operation" :options="operations" />
    <form @submit.prevent="submit">
      <p v-if="error" class="alert error">{{ error }}</p>
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
  </div>
</template>

<style scoped>
.operation-panel { font-size: .85rem; }
.operation-panel :deep(.tabs button) { font-size: .8rem; padding: 8px 4px; }
label, form > button { font-size: .82rem; }
</style>
