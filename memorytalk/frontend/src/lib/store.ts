import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type Locale = 'zh' | 'en';
const browserLocale = (): Locale => (typeof navigator !== 'undefined' && navigator.language.toLowerCase().startsWith('zh') ? 'zh' : 'en');

/** 登录态和偏好放一起存在浏览器里:token 每个请求都带;user / role 是登录时后端说的,只用来显示。setupRequired 不落盘。 */
interface Preferences {
  user: string; role: string; token: string; setupRequired: boolean;
  collapsed: boolean; worklets: Record<string, string>; locale: Locale;
  setSession: (user: string, role: string, token: string) => void; clearSession: () => void; setSetupRequired: (v: boolean) => void;
  toggleSidebar: () => void; selectWorklet: (work: string, worklet: string) => void; setLocale: (locale: Locale) => void;
}
export const usePreferences = create<Preferences>()(persist((set) => ({
  user: '', role: '', token: '', setupRequired: false, collapsed: false, worklets: {}, locale: browserLocale(),
  setSession: (user, role, token) => set({ user, role, token, setupRequired: false }),
  clearSession: () => set({ role: '', token: '' }),                      // 名字留着,登录页好预填
  setSetupRequired: setupRequired => set({ setupRequired }),
  toggleSidebar: () => set(s => ({ collapsed: !s.collapsed })),
  selectWorklet: (work, worklet) => set(s => ({ worklets: { ...s.worklets, [work]: worklet } })),
  setLocale: locale => set({ locale }),
}), { name: 'memorytalk.preferences.v2', partialize: s => ({ user: s.user, role: s.role, token: s.token, collapsed: s.collapsed, worklets: s.worklets, locale: s.locale }) }));
