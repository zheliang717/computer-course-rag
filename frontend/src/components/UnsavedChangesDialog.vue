<script setup lang="ts">
import DetailDialog from './DetailDialog.vue'
defineProps<{ labels: string[]; action: string; canStash?: boolean }>()
const emit = defineEmits<{ cancel: []; discard: []; stash: [] }>()
</script>
<template>
  <DetailDialog title="还有未保存的内容" close-label="保留修改并返回" size="small" alert @close="emit('cancel')"><p class="unsaved-explanation">{{ action }}前，请先处理以下修改。它们还没有提交到系统。</p><ul class="unsaved-groups"><li v-for="label in labels" :key="label">{{ label }}</li></ul><template #footer><button type="button" @click="emit('cancel')">保留修改，返回编辑</button><button v-if="canStash" type="button" @click="emit('stash')">暂存草稿并继续</button><button type="button" class="danger-soft" @click="emit('discard')">放弃这些修改并继续</button></template></DetailDialog>
</template>
<style scoped>.unsaved-explanation { color: #607792; font-size: 14px; line-height: 1.9; }.unsaved-groups { color: #436383; font-size: 13px; line-height: 2; padding-left: 20px; }button { font-size: 12px; padding: 10px 14px; }</style>
