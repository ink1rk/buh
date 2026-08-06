import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppShell } from '@/components/layout/AppShell'
import { DashboardPage } from '@/pages/DashboardPage'
import { GoalsPage } from '@/pages/GoalsPage'
import { AnalyticsPage } from '@/pages/AnalyticsPage'
import { CashflowPage } from '@/pages/CashflowPage'
import { DebtsPage } from '@/pages/DebtsPage'
import { SubscriptionsPage } from '@/pages/SubscriptionsPage'
import { CalendarPage } from '@/pages/CalendarPage'
import { InvestmentsPage } from '@/pages/InvestmentsPage'
import { AchievementsPage } from '@/pages/AchievementsPage'
import { PurchasePage } from '@/pages/PurchasePage'
import { SettingsPage } from '@/pages/SettingsPage'
import { ScenariosPage } from '@/pages/ScenariosPage'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      refetchOnWindowFocus: false,
    },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<DashboardPage />} />
            <Route path="goals" element={<GoalsPage />} />
            <Route path="analytics" element={<AnalyticsPage />} />
            <Route path="cashflow" element={<CashflowPage />} />
            <Route path="calendar" element={<CalendarPage />} />
            <Route path="debts" element={<DebtsPage />} />
            <Route path="subscriptions" element={<SubscriptionsPage />} />
            <Route path="investments" element={<InvestmentsPage />} />
            <Route path="achievements" element={<AchievementsPage />} />
            <Route path="purchase" element={<PurchasePage />} />
            <Route path="scenarios" element={<ScenariosPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
