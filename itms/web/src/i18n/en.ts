import type { Dictionary } from "./ru";

/**
 * Английский словарь. Переведена навигация и общая часть; остальные ключи
 * подхватываются из русского словаря, пока перевод не дописан.
 */
export const en: DeepPartial<Dictionary> = {
  app: {
    tagline: "IT infrastructure management",
    loading: "Loading…",
    empty: "No data",
    save: "Save",
    cancel: "Cancel",
    create: "Create",
    search: "Search",
    filters: "Filters",
    reset: "Reset",
    reason: "Reason for change",
    archive: "Archive",
    restore: "Restore",
    delete: "Delete",
    total: "Total",
  },
  nav: {
    dashboard: "Dashboard",
    objects: "Objects",
    devices: "Hardware",
    network: "Network",
    ipam: "IP addressing",
    diagrams: "Diagrams",
    racks: "Racks",
    projects: "Projects",
    analytics: "Analytics",
    power: "Power",
    catalog: "Model catalogue",
    locations: "Locations",
    documents: "Documentation",
    directory: "People",
    audit: "History",
    imports: "Import",
    search: "Search",
    settings: "Settings",
    logout: "Sign out",
    theme: "Theme",
    language: "Language",
    commandPalette: "Command palette",
  },
  notifications: {
    title: "Notifications",
    empty: "No notifications",
    readAll: "Mark all read",
    assigned: "Assignment",
    status: "Status",
    comment: "Comment",
    mention: "Mention",
  },
  auth: {
    title: "Sign in",
    email: "Email",
    password: "Password",
    submit: "Sign in",
  },
};

/**
 * Частичный словарь: любую ветку можно не переводить, а строковые литералы
 * русского словаря расширяются до обычного string.
 */
export type DeepPartial<T> = {
  [K in keyof T]?: T[K] extends string ? string : DeepPartial<T[K]>;
};
