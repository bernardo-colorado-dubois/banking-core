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
    <OpenAccountForm @opened="show" />
  </main>
</template>

<style scoped>
.narrow { max-width: 520px; }
</style>
