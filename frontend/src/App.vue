<script setup>
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { session } from './session'
import { api } from './api'
import BankLogo from './components/BankLogo.vue'

const router = useRouter()
const email = ref('')

// The token only carries the id and role; the email comes from the profile
watch(() => session.userId, async (userId) => {
  email.value = ''
  if (userId) {
    try {
      email.value = (await api.profile(userId)).email
    } catch {
      // The header still works without the email
    }
  }
}, { immediate: true })

function logout() {
  session.end()
  router.push({ name: 'login' })
}
</script>

<template>
  <header v-if="session.token" class="topbar">
    <div class="topbar-inner">
      <RouterLink to="/" class="brand"><BankLogo :size="22" />Banking core</RouterLink>
      <div class="user">
        <span class="badge">{{ session.role }}</span>
        <span class="muted email">{{ email }}</span>
        <button class="ghost" @click="logout">Log out</button>
      </div>
    </div>
  </header>
  <RouterView />
</template>

<style scoped>
.topbar { background: var(--surface); border-bottom: 1px solid var(--line); }
.topbar-inner { max-width: 1080px; margin: 0 auto; padding: 12px 16px; display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.brand { display: inline-flex; align-items: center; gap: 8px; font-weight: 700; color: var(--ink); letter-spacing: -.01em; }
.brand:hover { text-decoration: none; }
.brand svg { color: var(--accent); }
.user { display: flex; align-items: center; gap: 12px; font-size: .875rem; }
.user button { padding: 6px 12px; }
@media (max-width: 560px) {
  .email { display: none; }
}
</style>
