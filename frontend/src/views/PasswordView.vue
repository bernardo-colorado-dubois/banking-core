<script setup>
import { useRouter } from 'vue-router'
import { session } from '../session'
import PasswordForm from '../components/PasswordForm.vue'

const router = useRouter()
</script>

<template>
  <main class="page narrow">
    <div class="card">
      <h1>Change password</h1>
      <p v-if="session.mustChangePassword" class="muted lead">You must set a new password before continuing.</p>
      <PasswordForm @changed="router.push({ name: 'accounts' })" />
    </div>
  </main>
</template>

<style scoped>
.narrow { max-width: 440px; }
.lead { margin: 4px 0 20px; font-size: .9rem; }
h1 { margin-bottom: 16px; }
</style>
