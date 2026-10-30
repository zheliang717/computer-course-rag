<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = defineProps<{ name: string; identity: string; image?: string | null }>()
const failed = ref(false)
watch(() => props.image, () => { failed.value = false })
const initial = computed(() => Array.from(props.name.trim())[0]?.toUpperCase() || '我')
// A stable account-based palette keeps the default avatar consistent across devices.
const palette = computed(() => {
  let hash = 0
  for (const character of props.identity) hash = (hash * 31 + character.codePointAt(0)!) >>> 0
  return hash % 5
})
</script>

<template>
  <span class="profile-avatar" :class="`profile-avatar-${palette}`" aria-hidden="true"><img v-if="image && !failed" :src="image" alt="" draggable="false" @error="failed = true" /><template v-else>{{ initial }}</template></span>
</template>

<style scoped>
.profile-avatar { align-items: center; background: #e8efff; border: 1px solid #ffffffa6; border-radius: 50%; color: #385fc0; display: inline-flex; flex: none; font-size: 14px; font-weight: 750; height: 34px; justify-content: center; line-height: 1; user-select: none; width: 34px; }
.profile-avatar-1 { background: #eee8ff; color: #7352b8; }
.profile-avatar-2 { background: #ddf2ec; color: #2f7a67; }
.profile-avatar-3 { background: #fff0df; color: #a56530; }
.profile-avatar-4 { background: #fbe7ed; color: #b35476; }
.profile-avatar { overflow: hidden; }
.profile-avatar img { display: block; height: 100%; object-fit: cover; width: 100%; }
</style>
