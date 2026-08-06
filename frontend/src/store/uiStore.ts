import { create } from 'zustand'

type Theme = 'auto' | 'dark' | 'light'

interface UIState {
  theme: Theme
  chatOpen: boolean
  spotlightOpen: boolean
  healthOpen: boolean
  setTheme: (theme: Theme) => void
  toggleChat: () => void
  setChatOpen: (v: boolean) => void
  setSpotlightOpen: (v: boolean) => void
  setHealthOpen: (v: boolean) => void
  applyTheme: () => void
}

function resolveTheme(theme: Theme): 'dark' | 'light' {
  if (theme === 'auto') {
    return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
  }
  return theme
}

export const useUIStore = create<UIState>((set, get) => ({
  theme: (localStorage.getItem('pfa-theme') as Theme) || 'auto',
  chatOpen: true,
  spotlightOpen: false,
  healthOpen: false,
  setTheme: (theme) => {
    localStorage.setItem('pfa-theme', theme)
    set({ theme })
    get().applyTheme()
  },
  toggleChat: () => set((s) => ({ chatOpen: !s.chatOpen })),
  setChatOpen: (chatOpen) => set({ chatOpen }),
  setSpotlightOpen: (spotlightOpen) => set({ spotlightOpen }),
  setHealthOpen: (healthOpen) => set({ healthOpen }),
  applyTheme: () => {
    const mode = resolveTheme(get().theme)
    document.documentElement.classList.toggle('dark', mode === 'dark')
    document.documentElement.classList.toggle('light', mode === 'light')
  },
}))
