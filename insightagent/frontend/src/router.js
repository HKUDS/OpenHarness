import { createRouter, createWebHashHistory } from 'vue-router'
import { getToken } from './api'
import LoginView from './views/LoginView.vue'
import SessionsView from './views/SessionsView.vue'
import ChatView from './views/ChatView.vue'
import CapabilitiesView from './views/CapabilitiesView.vue'
import SettingsView from './views/SettingsView.vue'

const routes = [
  { path: '/', redirect: '/sessions' },
  { path: '/login', name: 'login', component: LoginView, meta: { public: true } },
  { path: '/sessions', name: 'sessions', component: SessionsView, meta: { tab: 'sessions' } },
  { path: '/chat/:id?', name: 'chat', component: ChatView, meta: { tab: 'sessions', immersive: true } },
  { path: '/capabilities', name: 'capabilities', component: CapabilitiesView, meta: { tab: 'capabilities' } },
  { path: '/settings', name: 'settings', component: SettingsView, meta: { tab: 'settings' } },
  { path: '/:pathMatch(.*)*', redirect: '/sessions' },
]

export const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach((to) => {
  if (!to.meta.public && !getToken()) return { name: 'login' }
  if (to.name === 'login' && getToken()) return { name: 'sessions' }
  return true
})
