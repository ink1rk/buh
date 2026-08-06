import { Outlet } from 'react-router-dom'
import { useEffect } from 'react'
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'
import { AIChat } from '@/components/ai/AIChat'
import { QuickInput } from '@/components/spotlight/QuickInput'
import { useUIStore } from '@/store/uiStore'
import { MobileNav } from './MobileNav'

export function AppShell() {
  const applyTheme = useUIStore((s) => s.applyTheme)

  useEffect(() => {
    applyTheme()
    const mq = window.matchMedia('(prefers-color-scheme: light)')
    const onChange = () => applyTheme()
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [applyTheme])

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="px-4 pt-4 lg:px-6 lg:pt-6">
          <TopBar />
        </div>
        <main className="min-w-0 flex-1 px-4 pb-24 lg:px-6 lg:pb-8">
          <Outlet />
        </main>
        <MobileNav />
      </div>
      <AIChat />
      <QuickInput />
    </div>
  )
}
