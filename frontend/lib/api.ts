import { createApi } from "@shared/api";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export const api = createApi(API_BASE_URL);

export { ApiError, queryKeys, REFRESH_INTERVAL_MS } from "@shared/api";
