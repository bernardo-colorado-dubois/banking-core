<script setup>
import { useRouter } from 'vue-router'
import PasswordForm from '../components/PasswordForm.vue'

const router = useRouter()
</script>

<template>
  <main class="page narrow">
    <PasswordForm @changed="router.push({ name: 'accounts' })" />
  </main>
</template>

<style scoped>
.narrow { max-width: 440px; }
</style>
