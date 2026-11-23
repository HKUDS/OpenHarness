<script setup>
import AppIcon from './AppIcon.vue'

defineProps({
  title: { type: String, default: '' },
  icon: { type: String, default: '' },
})
const emit = defineEmits(['close'])
</script>

<template>
  <Teleport to="body">
    <div class="mask" @click="emit('close')" />
    <div class="sheet" role="dialog">
      <div class="grab" />
      <div class="sheet-head">
        <AppIcon v-if="icon" :name="icon" :size="20" class="sheet-ico" />
        <span class="sheet-title">{{ title }}</span>
        <button class="icon-btn" @click="emit('close')">
          <AppIcon name="close" :size="16" />
        </button>
      </div>
      <slot />
    </div>
  </Teleport>
</template>
