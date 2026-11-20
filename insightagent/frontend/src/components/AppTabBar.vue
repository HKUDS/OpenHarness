<script setup>
import AppIcon from './AppIcon.vue'
import { useRoute } from 'vue-router'
import { tabs } from '../nav'

const route = useRoute()
</script>

<template>
  <nav class="tabbar">
    <router-link
      v-for="t in tabs"
      :key="t.key"
      :to="t.to"
      class="tab-item"
      :class="{ on: route.meta.tab === t.key }"
    >
      <AppIcon :name="t.icon" :stroke="route.meta.tab === t.key ? 1.9 : 1.5" />
      <span>{{ t.label }}</span>
    </router-link>
  </nav>
</template>
