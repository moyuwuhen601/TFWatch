<script setup>
import { computed, ref, watch } from 'vue'
import { iconLetter } from './format'

const props = defineProps({ icon: String, name: { type: String, required: true } })
const failed = ref(false)
const tone = computed(() => [...props.name].reduce((total, letter) => total + letter.codePointAt(0), 0) % 5)
watch(() => props.icon, () => { failed.value = false })
</script>

<template>
  <span class="app-icon" :class="'icon-tone-' + tone" aria-hidden="true">
    <img v-if="icon && !failed" :src="icon" alt="" loading="lazy" referrerpolicy="no-referrer" @error="failed = true">
    <span v-else>{{ iconLetter(name) }}</span>
  </span>
</template>
