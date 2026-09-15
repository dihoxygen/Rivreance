"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

import { REFRESH_INTERVAL_MS } from "@/lib/api";

export function Providers({ children }: { children: React.ReactNode }) {
  // USGS data only changes every 15 minutes and the API caches for the same window,
  // so refetching faster would add load without adding information.
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: REFRESH_INTERVAL_MS,
            gcTime: 2 * REFRESH_INTERVAL_MS,
            refetchInterval: REFRESH_INTERVAL_MS,
            refetchOnWindowFocus: false,
            retry: 1,
          },
        },
      }),
  );

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
