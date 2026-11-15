<script setup>
import { states } from './format'

defineProps({ status: { type: String, required: true }, pending: Boolean })
</script>

<template>
  <span class="status-pill" :class="'status-' + status">
    <span></span>{{ pending ? '待检测' : (states[status] || states.unknown) }}
  </span>
</template>
