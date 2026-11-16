// Amounts travel as text with 2 decimals ("1234.50") and stay text here:
// converting them to Number would bring back the float errors the API avoids.
const AMOUNT = /^\d+(\.\d{1,2})?$/

export function validAmount(value) {
  const amount = value.trim()
  return AMOUNT.test(amount) && /[1-9]/.test(amount)
}

export function money(amount) {
  const [integer, decimals = '00'] = amount.split('.')
  return `$${integer.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}.${decimals.padEnd(2, '0')}`
}

const dateFormat = new Intl.DateTimeFormat('es-MX', { dateStyle: 'medium', timeStyle: 'short' })

export function date(iso) {
  return dateFormat.format(new Date(iso))
}

export function shortId(id) {
  return id.slice(0, 8)
}
