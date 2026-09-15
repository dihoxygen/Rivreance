import Constants from "expo-constants";

import { createApi } from "@shared/api";

/**
 * A phone cannot reach the laptop's `localhost`, but Expo records the host it served
 * the bundle from, and in development the API runs beside it. Set
 * `EXPO_PUBLIC_API_BASE_URL` to point at a deployed backend instead.
 */
function resolveBaseUrl(): string {
  const configured = process.env.EXPO_PUBLIC_API_BASE_URL;
  if (configured) return configured;

  const devHost = Constants.expoConfig?.hostUri?.split(":")[0];
  if (devHost) return `http://${devHost}:8000/api/v1`;

  return "http://localhost:8000/api/v1";
}

export const API_BASE_URL = resolveBaseUrl();

export const api = createApi(API_BASE_URL);

export { ApiError, queryKeys, REFRESH_INTERVAL_MS } from "@shared/api";
