<script setup>
import { date, money } from '../format'

defineProps({ accounts: { type: Array, required: true } })
</script>

<template>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Alias</th>
          <th>Class</th>
          <th>Holder</th>
          <th>Opened</th>
          <th class="num">Balance</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="account in accounts" :key="account.id">
          <td><RouterLink :to="{ name: 'account', params: { id: account.id } }">{{ account.alias }}</RouterLink></td>
          <td><span class="badge">{{ account.account_class }}</span></td>
          <td>{{ account.holder }}</td>
          <td class="muted">{{ date(account.created_at) }}</td>
          <td class="num mono">{{ money(account.balance) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
