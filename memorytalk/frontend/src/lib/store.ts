import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type Locale = 'zh' | 'en';
const browserLocale = (): Locale => (typeof navigator !== 'undefined' && navigator.language.toLowerCase().startsWith('zh') ? 'zh' : 'en');

interface Preferences {
  user: string; collapsed: boolean; sessions: Record<string, string>; locale: Locale;
  setUser: (user: string) => void; toggleSidebar: () => void;
  selectSession: (work: string, session: string) => void; setLocale: (locale: Locale) => void;
}
export const usePreferences = create<Preferences>()(persist((set) => ({
  user: '', collapsed: false, sessions: {}, locale: browserLocale(),
  setUser: user => set({ user }),
  toggleSidebar: () => set(s => ({ collapsed: !s.collapsed })),
  selectSession: (work, session) => set(s => ({ sessions: { ...s.sessions, [work]: session } })),
  setLocale: locale => set({ locale }),
}), { name: 'memorytalk.preferences.v1' }));
