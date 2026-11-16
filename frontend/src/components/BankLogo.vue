<script setup>
defineProps({ size: { type: Number, default: 24 } })
</script>

<!-- Pediment with a coin, four columns and two steps; currentColor follows the theme -->
<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path fill-rule="evenodd" d="M12 2 22 7v2H2V7Zm-1.3 4.3a1.3 1.3 0 1 0 2.6 0 1.3 1.3 0 1 0-2.6 0Z" />
    <rect x="4.5" y="10" width="2" height="8" />
    <rect x="9" y="10" width="2" height="8" />
    <rect x="13" y="10" width="2" height="8" />
    <rect x="17.5" y="10" width="2" height="8" />
    <rect x="3" y="19" width="18" height="1.5" />
    <rect x="2" y="21.5" width="20" height="1.5" />
  </svg>
</template>
