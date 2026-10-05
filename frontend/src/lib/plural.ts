/**
 * Русские окончания после числа: 1 операция, 2 операции, 5 операций.
 *
 * Английские шаблоны склонять не умеют, и на страницах оседало «2 подключение»
 * и «2273 операций» — мелочь, по которой видно, что цифры подставлены машиной.
 */
export function plural(count: number, one: string, few: string, many: string): string {
  const n = Math.abs(Math.trunc(count))
  const teens = n % 100
  if (teens >= 11 && teens <= 14) return many
  const last = n % 10
  if (last === 1) return one
  if (last >= 2 && last <= 4) return few
  return many
}

/** Число вместе со склонённым словом: «2273 операции». */
export function counted(count: number, one: string, few: string, many: string): string {
  return `${count.toLocaleString('ru-RU')} ${plural(count, one, few, many)}`
}
