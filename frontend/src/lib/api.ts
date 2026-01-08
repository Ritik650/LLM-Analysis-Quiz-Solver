// Thin API client. Stores the JWT in localStorage and attaches it as a Bearer
// header. VITE_API_BASE lets the deployed dashboard (Vercel) point at the HF
// Space; in dev it's empty and Vite proxies same-origin paths to :7860.

import type { RunDetail, RunSummary } from "../types";

const BASE = import.meta.env.VITE_API_BASE ?? "";
const TOKEN_KEY = "quiz_solver_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const resp = await fetch(`${BASE}${path}`, { ...options, headers });
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      detail = (await resp.json()).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  if (resp.status === 204) return undefined as T;
  return resp.json() as Promise<T>;
}

export interface AuthResult {
  access_token: string;
  email: string;
}

export const api = {
  register: (email: string, password: string) =>
    request<AuthResult>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  login: (email: string, password: string) =>
    request<AuthResult>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  me: () => request<{ id: number; email: string }>("/auth/me"),

  solve: (url: string) =>
    request<{ status: string; run_id: string; stream: string }>("/solve", {
      method: "POST",
      body: JSON.stringify({ url }),
    }),

  listRuns: () => request<{ runs: RunSummary[] }>("/runs"),

  getRun: (id: string) => request<RunDetail>(`/runs/${id}`),
};

export const apiBase = BASE;
