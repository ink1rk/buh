export interface Greeting {
  greeting: string
  subtitle: string
  user_name: string
  period: string
}

export interface MotivationalQuote {
  text: string
  author: string
  theme: string
}

export interface DailyWidget {
  id: number
  shown_on: string
  widget_type: string
  title: string
  body: string
  author: string
  source: string
}

export interface HealthFactor {
  name: string
  score: number
  weight: number
  explanation: string
}

export interface FinancialHealth {
  score: number
  label: string
  factors: HealthFactor[]
  summary: string
}

export interface Account {
  id: number
  name: string
  account_type: string
  balance: number
  currency: string
  color: string
  icon: string
  is_active: boolean
  notes: string
  sort_order: number
}

export interface DashboardBalances {
  total: number
  cash: number
  cards: number
  bank: number
  investments: number
  crypto: number
  savings: number
  reserve: number
  debts_owed: number
  debts_owing: number
  income_month: number
  expense_month: number
  accounts: Account[]
}

export interface Insight {
  title: string
  body: string
  insight_type: string
  severity: string
  category: string
}

export interface DashboardData {
  greeting: Greeting
  quote: MotivationalQuote
  widget: DailyWidget
  health: FinancialHealth
  balances: DashboardBalances
  insights: Insight[]
  focus_of_day: string
}

export interface Goal {
  id: number
  title: string
  description: string
  target_amount: number
  current_amount: number
  monthly_contribution: number
  deadline: string | null
  icon: string
  color: string
  category: string
  priority: number
  is_active: boolean
  probability: number
  remaining: number
  progress_pct: number
  months_left: number | null
}

export interface Transaction {
  id: number
  amount: number
  currency: string
  category: string
  subcategory: string
  description: string
  merchant: string
  account_id: number | null
  transaction_type: string
  occurred_on: string
  tags: string
  source: string
  raw_input: string
}

export interface ChatResponse {
  reply: string
  suggestions: string[]
  actions: Record<string, unknown>[]
  memories_used: string[]
}

export interface PurchaseAnalysis {
  item: string
  price: number
  capital_pct: number
  work_hours: number
  life_days: number
  months_of_savings: number
  goal_impact: string
  alternatives: string[]
  wait_advice: string
  recommendation: string
  score: number
  postpone_available: boolean
}
