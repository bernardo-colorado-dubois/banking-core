<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { session } from '../session'
import AccountsTable from '../components/AccountsTable.vue'

const router = useRouter()

const accounts = ref([])
const error = ref('')
const forbidden = ref(false)
const loading = ref(true)

// A client receives only their own accounts from the same endpoint
const ownOnly = computed(() => accounts.value.length > 0 && accounts.value.every((account) => account.holder_id === session.userId))

onMounted(async () => {
  try {
    accounts.value = (await api.accounts()).accounts
    // With a single account of their own there is nothing to choose: go straight to it
    if (ownOnly.value && accounts.value.length === 1) {
      router.replace({ name: 'account', params: { id: accounts.value[0].id } })
    }
  } catch (failure) {
    forbidden.value = failure.status === 403
    error.value = failure.message
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <main class="page">
    <div class="page-head">
      <div>
        <h1>{{ ownOnly ? 'Your accounts' : 'Accounts' }}</h1>
        <p class="muted">{{ ownOnly ? 'Your accounts with their current balance.' : 'Every NOSTRO and VOSTRO account with its current balance.' }}</p>
      </div>
      <RouterLink v-if="!forbidden && !ownOnly" :to="{ name: 'open-account' }" class="button">Open account</RouterLink>
    </div>

    <p v-if="loading" class="muted">Loading…</p>
    <div v-else-if="forbidden" class="card">
      <h2>No access to the account list</h2>
      <p class="muted">Your role cannot list accounts.</p>
    </div>
    <p v-else-if="error" class="alert error">{{ error }}</p>
    <div v-else-if="!accounts.length" class="card">
      <p class="muted">There are no accounts yet.</p>
    </div>
    <div v-else class="card flush">
      <AccountsTable :accounts="accounts" />
    </div>
  </main>
</template>

<style scoped>
.flush { padding: 8px 12px; }
</style>
