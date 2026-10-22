<script setup>
import { useRouter } from 'vue-router'
import OpenAccountForm from '../components/OpenAccountForm.vue'

const router = useRouter()

function show(account) {
  router.push({ name: 'account', params: { id: account.id } })
}
</script>

<template>
  <main class="page narrow">
    <RouterLink to="/" class="back">← Accounts</RouterLink>
    <div class="card">
      <h1>Open account</h1>
      <OpenAccountForm @opened="show" />
    </div>
  </main>
</template>

<style scoped>
.narrow { max-width: 520px; }
h1 { margin-bottom: 20px; }
</style>
