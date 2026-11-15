<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { Link, Plus } from 'lucide-vue-next'
import { api } from './api'

const props = defineProps({ appId: Number })
const emit = defineEmits(['submitted', 'cancel'])
const router = useRouter()
const url = ref('')
const name = ref('')
const error = ref('')
const saving = ref(false)

async function submit() {
  error.value = ''
  saving.value = true
  try {
    const result = await api('/apps', {
      method: 'POST', body: { url: url.value.trim(), name: name.value.trim() || null, app_id: props.appId || null },
    })
    emit('submitted', result)
    url.value = ''
    name.value = ''
    await router.push({ path: '/apps/' + result.app_id, query: { invite: result.code } })
  } catch (err) {
    error.value = err.message
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <form class="form-stack" @submit.prevent="submit">
    <label>TestFlight 邀请链接
      <div class="field-icon"><Link :size="17" /><input v-model="url" type="url" placeholder="https://testflight.apple.com/join/…" maxlength="1000" required></div>
    </label>
    <label v-if="!appId">软件名称 <span class="muted normal">（选填）</span>
      <input v-model="name" maxlength="180" placeholder="留空时会尝试从 TestFlight 识别">
    </label>
    <p v-if="error" class="feedback error" role="alert">{{ error }}</p>
    <div class="form-actions">
      <button type="button" class="btn btn-secondary" @click="$emit('cancel')">取消</button>
      <button class="btn btn-dark" :disabled="saving"><Plus :size="17" /> {{ saving ? '正在添加…' : '添加邀请' }}</button>
    </div>
  </form>
</template>
