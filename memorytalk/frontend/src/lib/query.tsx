import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from '@/components/ui/sonner';
import type { ReactNode } from 'react';
import { ApiError } from './api';

export const queryClient = new QueryClient({ defaultOptions: {
  queries: {
    staleTime: 5_000, refetchOnWindowFocus: true,
    retry: (count, error) => count < 1 && !(error instanceof ApiError && error.status >= 400 && error.status < 500),
  },
  mutations: { retry: false },
} });
export function AppProviders({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}<Toaster position="bottom-right" richColors closeButton /></QueryClientProvider>;
}
