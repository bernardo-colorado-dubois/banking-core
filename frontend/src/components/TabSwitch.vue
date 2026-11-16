<script setup>
// Segmented tabs bound with v-model; options maps each value to its label
defineProps({ options: { type: Object, required: true } })
const selected = defineModel({ type: String, required: true })
</script>

<template>
  <div class="tabs">
    <button
      v-for="(label, value) in options" :key="value" type="button"
      :class="{ active: selected === value }" @click="selected = value"
    >{{ label }}</button>
  </div>
</template>
