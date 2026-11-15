<script setup>
import { ref, watch } from 'vue'
import { CalendarDays, Clock3, History, Radio } from 'lucide-vue-next'
import { api } from './api'
import { dateLabel, durationLabel, states } from './format'
import StatusPill from './StatusPill.vue'

const props = defineProps({ code: { type: String, required: true }, checkedAt: Number })
const range = ref('30')
const data = ref(null)
const busy = ref(false)
const paging = ref(false)
const error = ref('')
const moreError = ref('')

watch([() => props.code, () => props.checkedAt, range], async (_, __, onCleanup) => {
  const abort = new AbortController()
  onCleanup(() => abort.abort())
  busy.value = true
  error.value = ''
  moreError.value = ''
  data.value = null
  try {
    data.value = await api('/invites/' + props.code + '/timeline?days=' + range.value, { signal: abort.signal })
  } catch (err) {
    if (!abort.signal.aborted) error.value = err.message
  } finally {
    if (!abort.signal.aborted) busy.value = false
  }
}, { immediate: true })

async function more() {
  if (!data.value?.next_before) return
  const current = data.value
  paging.value = true
  moreError.value = ''
  try {
    const result = await api('/invites/' + props.code + '/timeline?days=' + range.value + '&before=' + current.next_before)
    if (current === data.value) {
      current.events.push(...result.events)
      current.next_before = result.next_before
    }
  } catch (error) {
    if (current === data.value) moreError.value = error.message
  } finally {
    paging.value = false
  }
}
</script>

<template>
  <section class="panel timeline">
    <div class="section-heading compact">
      <div><div class="section-icon"><History :size="19" /></div><div><h2>开放时间线</h2><p>记录每次检测到的状态变化。</p></div></div>
      <div class="filters" aria-label="时间范围">
        <button v-for="[key, text] in [['7','7 天'], ['30','30 天'], ['90','90 天'], ['all','全部']]" :key="key" type="button" :aria-pressed="range === key" @click="range = key">{{ text }}</button>
      </div>
    </div>
    <p v-if="busy" role="status" class="muted">正在加载时间线…</p>
    <p v-else-if="error" class="feedback error" role="alert">{{ error }}</p>
    <template v-else-if="data">
      <dl class="metrics">
        <div><dt><Radio :size="16" /> 观测开放区间</dt><dd>{{ data.open_periods }} <small>次</small></dd></div>
        <div><dt><Clock3 :size="16" /> 平均观测开放时长</dt><dd>{{ durationLabel(data.average_open_seconds) }}</dd></div>
        <div><dt><CalendarDays :size="16" /> 最近检测到开放</dt><dd>{{ dateLabel(data.last_open) }}</dd></div>
      </dl>
      <div class="timeline-chart">
        <div class="time-bars" aria-hidden="true">
          <span v-for="(point, index) in data.points" :key="index" :class="'bar-' + (point?.status || 'empty')"
                :title="point ? dateLabel(point.at) + ' · ' + states[point.status] : '无采样'" />
        </div>
        <div class="time-ends"><span>{{ dateLabel(data.start, true) }}</span><span>{{ dateLabel(data.end, true) }}</span></div>
        <div class="legend">
          <span v-for="[key, label] in [...Object.entries(states), ['empty','无采样']]" :key="key"><i :class="'bar-' + key"></i>{{ label }}</span>
        </div>
      </div>
      <p class="caption">时间轴显示每格最后一次采样。这里的时间是检测时间，开放时长根据相邻的开放采样估计。</p>
      <h3 class="history-title">最近状态变化</h3>
      <p v-if="!data.events.length" class="muted">此时间范围内暂无状态记录。</p>
      <ol v-else class="history-list">
        <li v-for="event in data.events" :key="event.id">
          <span class="history-node" :class="'dot-' + event.status"></span>
          <div><StatusPill :status="event.status" /><p>{{ event.previous ? '此前状态 · ' + states[event.previous] : '首次检测' }}</p></div>
          <time :datetime="new Date(event.checked_at * 1000).toISOString()">{{ dateLabel(event.checked_at) }}</time>
        </li>
      </ol>
      <p v-if="moreError" class="feedback error" role="alert">{{ moreError }}</p>
      <button v-if="data.next_before" type="button" class="btn btn-secondary btn-small" :disabled="paging" @click="more">加载更早的记录</button>
    </template>
  </section>
</template>
