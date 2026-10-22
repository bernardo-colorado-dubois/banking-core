<script setup>
import { useRoute, useRouter } from 'vue-router'
import LoginForm from '../components/LoginForm.vue'

const route = useRoute()
const router = useRouter()

function enter(result) {
  router.push(result.must_change_password ? { name: 'password' } : { name: 'accounts' })
}
</script>

<template>
  <main class="center">
    <LoginForm :expired="Boolean(route.query.expired)" @logged-in="enter" />
  </main>
</template>

<style scoped>
.center { min-height: 100vh; display: grid; place-items: center; padding: 16px; }
</style>
