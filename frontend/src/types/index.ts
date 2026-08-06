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

export interface LivingScreenLine {
  icon: string
  text: string
  tone: 'positive' | 'neutral' | 'warning'
}

export interface ProactiveAlert {
  icon: string
  title: string
  body: string
  tone: 'positive' | 'neutral' | 'warning'
  category: string
}

export interface DailyChallenge {
  id?: number
  title: string
  body: string
  category: string
  is_completed?: boolean
}

export interface DashboardData {
  greeting: Greeting
  quote: MotivationalQuote
  widget: DailyWidget
  health: FinancialHealth
  balances: DashboardBalances
  insights: Insight[]
  focus_of_day: string
  net_worth: number
  net_worth_delta_today: number
  net_worth_delta_month: number
  net_worth_delta_year: number
  streak_days: number
  living_screen: LivingScreenLine[]
  daily_challenge: DailyChallenge | null
  proactive_alerts: ProactiveAlert[]
}

export interface CapitalSlice {
  key: string
  label: string
  value: number
  color: string
}

export interface AssetItem {
  id: number
  name: string
  asset_type: string
  value: number
  currency: string
  icon: string
  color: string
  notes: string
}

export interface CapitalMap {
  total_capital: number
  net_capital: number
  slices: CapitalSlice[]
  total_debts: number
  assets: AssetItem[]
}

export interface NetWorthPoint {
  date: string
  net_worth: number
  rating: string
}

export interface NetWorthData {
  current: number
  delta: { today: number; month: number; year: number }
  history: NetWorthPoint[]
  capital_map: CapitalMap
}

export interface ContributionDay {
  date: string
  rating: 'good' | 'neutral' | 'overspend' | 'empty'
  net: number
}

export interface TimelineItem {
  id: string
  icon: string
  title: string
  amount: number | null
  color: string
  time: string
}

export interface TimelineGroup {
  label: string
  date: string
  items: TimelineItem[]
}

export interface HabitScore {
  key: string
  label: string
  score: number
  explanation: string
}

export interface HabitsProfile {
  scores: HabitScore[]
  overall: number
  archetype: string
  summary: string
}

export interface RiskItem {
  key: string
  label: string
  level: number
  status: 'low' | 'medium' | 'high'
  explanation: string
}

export interface RisksProfile {
  items: RiskItem[]
  overall_risk: number
  summary: string
}

export interface HappinessInsight {
  category: string
  avg_rating: number
  count: number
  verdict: string
}

export interface PurchaseRating {
  id: number
  transaction_id: number | null
  item: string
  price: number
  category: string
  initial_rating: number | null
  followup_rating: number | null
  follow_up_on: string | null
  followed_up: boolean
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
  coffee_equivalent: number
  goal_impact: string
  alternatives: string[]
  wait_advice: string
  recommendation: string
  score: number
  postpone_available: boolean
  challenge_questions: string[]
  twin_opinion: string
  related_memory: string
}
