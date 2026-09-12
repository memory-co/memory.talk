import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface Preferences {
  user: string; collapsed: boolean; sessions: Record<string, string>;
  setUser: (user: string) => void; toggleSidebar: () => void;
  selectSession: (work: string, session: string) => void;
}
export const usePreferences = create<Preferences>()(persist((set) => ({
  user: '', collapsed: false, sessions: {},
  setUser: user => set({ user }),
  toggleSidebar: () => set(s => ({ collapsed: !s.collapsed })),
  selectSession: (work, session) => set(s => ({ sessions: { ...s.sessions, [work]: session } })),
}), { name: 'memorytalk.preferences.v1' }));
