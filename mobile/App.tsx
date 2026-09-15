import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { REFRESH_INTERVAL_MS } from "@/lib/api";
import { MapScreen } from "@/screens/MapScreen";

/**
 * The API caches for the same window, so refetching more often would only return
 * identical payloads while spending a phone's battery and data.
 */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: REFRESH_INTERVAL_MS,
      refetchInterval: REFRESH_INTERVAL_MS,
      retry: 1,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <SafeAreaProvider>
        <StatusBar style="light" />
        <MapScreen />
      </SafeAreaProvider>
    </QueryClientProvider>
  );
}
