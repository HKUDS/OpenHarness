<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AppTabBar from './components/AppTabBar.vue'
import AppIcon from './components/AppIcon.vue'
import DesktopShell from './desktop/DesktopShell.vue'
import { useViewport } from './composables/useViewport'
import { tabs } from './nav'
import { auth, toasts } from './store'

const route = useRoute()
const { isDesktop } = useViewport()

const showTab = computed(() => Boolean(route.meta.tab))
const showTabBar = computed(() => showTab.value && !route.meta.immersive)
const desktopApp = computed(() => isDesktop.value && showTab.value)
const initial = computed(() => {
  const name = auth.user?.display_name || auth.user?.username || ''
  return name ? name.trim().charAt(0).toUpperCase() : '?'
})
</script>

<template>
  <DesktopShell v-if="desktopApp" />

  <div v-else class="shell" :class="{ 'shell-bare': !showTab }">
    <aside v-if="showTab" class="sidebar">
      <router-link to="/sessions" class="brand">
        <span class="brand-logo">
          <AppIcon name="sparkles" :size="19" :stroke="1.9" />
        </span>
        <span class="brand-name">InsightAgent</span>
      </router-link>

      <nav class="side-nav">
        <router-link
          v-for="t in tabs"
          :key="t.key"
          :to="t.to"
          class="side-item"
          :class="{ on: route.meta.tab === t.key }"
        >
          <AppIcon :name="t.icon" :size="18" :stroke="route.meta.tab === t.key ? 1.9 : 1.6" />
          <span>{{ t.label }}</span>
        </router-link>
      </nav>

      <div class="side-user">
        <span class="side-avatar">{{ initial }}</span>
        <span class="side-user-main">
          <span class="side-user-name">{{ auth.user?.display_name || auth.user?.username || '未登录' }}</span>
          <span class="side-user-sub">@{{ auth.user?.username || '-' }}</span>
        </span>
      </div>
    </aside>

    <div class="content">
      <router-view v-slot="{ Component }">
        <keep-alive :include="['SessionsView', 'CapabilitiesView']">
          <component :is="Component" />
        </keep-alive>
      </router-view>

      <AppTabBar v-if="showTabBar" />
    </div>
  </div>

  <div class="toast-wrap">
    <div v-for="t in toasts" :key="t.id" class="toast">
      <AppIcon v-if="t.icon" name="check" :size="15" class="ok" />
      <span>{{ t.message }}</span>
    </div>
  </div>
</template>
