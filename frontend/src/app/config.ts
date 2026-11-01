// Single place to configure the backend. Override with NEXT_PUBLIC_BACKEND_URL (e.g. in frontend/.env.local).
export const BACKEND_URL = (process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000").replace(/\/+$/, "");
