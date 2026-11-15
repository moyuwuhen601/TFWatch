import assert from 'node:assert/strict'
import { test } from 'node:test'
import { dateLabel, durationLabel, iconLetter } from './format.js'

test('timeline uses an em dash for missing observations', () => {
  assert.equal(dateLabel(null), '—')
  assert.equal(durationLabel(null), '—')
  assert.equal(durationLabel(30), '< 1 分钟')
  assert.equal(durationLabel(8100), '2 小时 15 分钟')
})

test('fallback app icon handles non-Latin names and Unicode symbols', () => {
  assert.equal(iconLetter(' test'), 'T')
  assert.equal(iconLetter('飞行'), '飞')
  assert.equal(iconLetter('🚀 Beta'), '🚀')
})
