import { createRouter, createWebHistory } from 'vue-router'
import { session } from './session'
import LoginView from './views/LoginView.vue'
import PasswordView from './views/PasswordView.vue'
import AccountsView from './views/AccountsView.vue'
import AccountView from './views/AccountView.vue'
import OpenAccountView from './views/OpenAccountView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginView, meta: { public: true } },
    { path: '/password', name: 'password', component: PasswordView },
    { path: '/', name: 'accounts', component: AccountsView },
    { path: '/accounts/new', name: 'open-account', component: OpenAccountView },
    { path: '/account/:id', name: 'account', component: AccountView, props: true },
    { path: '/:pathMatch(.*)*', redirect: '/' }
  ]
})

router.beforeEach((to) => {
  if (to.meta.public) {
    return session.token && to.name === 'login' ? { name: 'accounts' } : true
  }
  if (!session.token) {
    return { name: 'login' }
  }
  // While the password is pending the API answers 403 everywhere else
  if (session.mustChangePassword && to.name !== 'password') {
    return { name: 'password' }
  }
  return true
})

export default router
