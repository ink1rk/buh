/** Единый словарь категорий: в базе они кодами, человеку нужны словами. */

export interface CategoryInfo {
  slug: string
  label: string
  color: string
  /** Расход, доход или и то и другое — чтобы в форме не предлагать лишнего. */
  kind: 'expense' | 'income' | 'both'
}

/**
 * Тот же список есть на бэкенде (`app/services/categories.py`): там он
 * подписывает подсказки и диаграммы. Категории в выписке ставит бэкенд, так
 * что пропуск здесь виден сразу — в списке операций всплывает латинский код.
 */
export const CATEGORIES: CategoryInfo[] = [
  { slug: 'groceries', label: 'Продукты', color: '#34d399', kind: 'expense' },
  { slug: 'cafe', label: 'Кофе и перекусы', color: '#fbbf24', kind: 'expense' },
  { slug: 'restaurants', label: 'Кафе и рестораны', color: '#f87171', kind: 'expense' },
  { slug: 'transport', label: 'Транспорт', color: '#60a5fa', kind: 'expense' },
  { slug: 'travel', label: 'Путешествия', color: '#22d3ee', kind: 'expense' },
  { slug: 'housing', label: 'Жильё', color: '#a78bfa', kind: 'expense' },
  { slug: 'home', label: 'Дом и ремонт', color: '#a78bfa', kind: 'expense' },
  { slug: 'utilities', label: 'ЖКХ и связь', color: '#7dd3fc', kind: 'expense' },
  { slug: 'subscriptions', label: 'Подписки', color: '#c084fc', kind: 'expense' },
  { slug: 'health', label: 'Здоровье', color: '#2dd4bf', kind: 'expense' },
  { slug: 'beauty', label: 'Красота', color: '#f0abfc', kind: 'expense' },
  { slug: 'clothes', label: 'Одежда', color: '#fb7185', kind: 'expense' },
  { slug: 'gadgets', label: 'Техника', color: '#818cf8', kind: 'expense' },
  { slug: 'shopping', label: 'Покупки', color: '#f59e0b', kind: 'expense' },
  { slug: 'entertainment', label: 'Развлечения', color: '#e879f9', kind: 'expense' },
  { slug: 'education', label: 'Образование', color: '#a3e635', kind: 'expense' },
  { slug: 'kids', label: 'Дети', color: '#fda4af', kind: 'expense' },
  { slug: 'pets', label: 'Питомцы', color: '#facc15', kind: 'expense' },
  { slug: 'services', label: 'Услуги', color: '#cbd5f5', kind: 'expense' },
  { slug: 'taxes', label: 'Налоги и штрафы', color: '#94a3b8', kind: 'expense' },
  { slug: 'insurance', label: 'Страхование', color: '#64748b', kind: 'expense' },
  { slug: 'fees', label: 'Комиссии банка', color: '#9ca3af', kind: 'expense' },
  { slug: 'cash', label: 'Наличные', color: '#fcd34d', kind: 'expense' },
  { slug: 'salary', label: 'Зарплата', color: '#4ade80', kind: 'income' },
  { slug: 'cashback', label: 'Кэшбэк', color: '#86efac', kind: 'income' },
  { slug: 'interest', label: 'Проценты по счёту', color: '#5eead4', kind: 'income' },
  { slug: 'refunds', label: 'Возвраты', color: '#67e8f9', kind: 'income' },
  { slug: 'other_income', label: 'Прочие поступления', color: '#a7f3d0', kind: 'income' },
  { slug: 'transfers', label: 'Переводы', color: '#93c5fd', kind: 'both' },
  { slug: 'investments', label: 'Инвестиции', color: '#38bdf8', kind: 'both' },
  { slug: 'savings', label: 'Накопления', color: '#fbbf24', kind: 'both' },
  { slug: 'other', label: 'Прочие расходы', color: '#94a3b8', kind: 'both' },
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
