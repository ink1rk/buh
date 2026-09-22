/** Единый словарь категорий: в базе они кодами, человеку нужны словами. */

export interface CategoryInfo {
  slug: string
  label: string
  color: string
  /** Расход, доход или и то и другое — чтобы в форме не предлагать лишнего. */
  kind: 'expense' | 'income' | 'both'
}

export const CATEGORIES: CategoryInfo[] = [
  { slug: 'groceries', label: 'Продукты', color: '#34d399', kind: 'expense' },
  { slug: 'cafe', label: 'Кофе и перекусы', color: '#fbbf24', kind: 'expense' },
  { slug: 'restaurants', label: 'Кафе и рестораны', color: '#f87171', kind: 'expense' },
  { slug: 'transport', label: 'Транспорт', color: '#60a5fa', kind: 'expense' },
  { slug: 'housing', label: 'Жильё', color: '#a78bfa', kind: 'expense' },
  { slug: 'subscriptions', label: 'Подписки', color: '#c084fc', kind: 'expense' },
  { slug: 'health', label: 'Здоровье', color: '#2dd4bf', kind: 'expense' },
  { slug: 'gadgets', label: 'Техника', color: '#818cf8', kind: 'expense' },
  { slug: 'salary', label: 'Зарплата', color: '#4ade80', kind: 'income' },
  { slug: 'investments', label: 'Инвестиции', color: '#38bdf8', kind: 'both' },
  { slug: 'savings', label: 'Накопления', color: '#fbbf24', kind: 'both' },
  { slug: 'other', label: 'Другое', color: '#94a3b8', kind: 'both' },
]

const BY_SLUG = new Map(CATEGORIES.map((c) => [c.slug, c]))

export function categoryLabel(slug: string): string {
  return BY_SLUG.get(slug)?.label || slug || 'Без категории'
}

export function categoryColor(slug: string): string {
  return BY_SLUG.get(slug)?.color || '#94a3b8'
}

export function categoriesFor(kind: 'income' | 'expense'): CategoryInfo[] {
  return CATEGORIES.filter((c) => c.kind === kind || c.kind === 'both')
}
