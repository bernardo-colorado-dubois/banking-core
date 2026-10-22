<script setup>
import { useRoute, useRouter } from 'vue-router'
import BankLogo from '../components/BankLogo.vue'
import LoginForm from '../components/LoginForm.vue'

const route = useRoute()
const router = useRouter()

function enter(result) {
  router.push(result.must_change_password ? { name: 'password' } : { name: 'accounts' })
}
</script>

<template>
  <main class="center">
    <div class="card box">
      <BankLogo :size="44" class="logo" />
      <h1>Banking core</h1>
      <p class="muted lead">Log in to manage accounts and movements.</p>
      <LoginForm :expired="Boolean(route.query.expired)" @logged-in="enter" />
    </div>
  </main>
</template>

<style scoped>
.center { min-height: 100vh; display: grid; place-items: center; padding: 16px; }
.box { width: 100%; max-width: 380px; }
.logo { color: var(--accent); margin-bottom: 12px; }
.lead { margin: 4px 0 24px; font-size: .9rem; }
</style>
