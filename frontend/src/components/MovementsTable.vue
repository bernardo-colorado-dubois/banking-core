<script setup>
import { date, money, shortId } from '../format'

// Movements arrive in the order they are shown; the reverse column only appears with canReverse
defineProps({
  movements: { type: Array, required: true },
  canReverse: { type: Boolean, default: false },
})
defineEmits(['reverse'])
</script>

<template>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Date</th>
          <th>Type</th>
          <th>Transaction</th>
          <th class="num">Amount</th>
          <th class="num">Balance</th>
          <th v-if="canReverse"></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="movement in movements" :key="movement.movement_id">
          <td class="muted">{{ date(movement.created_at) }}</td>
          <td>{{ movement.type }}</td>
          <td class="mono muted" :title="movement.transaction_id">{{ shortId(movement.transaction_id) }}</td>
          <td class="num mono" :class="movement.entry_type === 'CREDIT' ? 'credit' : 'debit'">
            {{ movement.entry_type === 'CREDIT' ? '+' : '−' }}{{ money(movement.amount) }}
          </td>
          <td class="num mono">{{ money(movement.balance) }}</td>
          <td v-if="canReverse" class="num">
            <button v-if="movement.type !== 'REVERSAL'" class="danger" @click="$emit('reverse', movement)">Reverse</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
