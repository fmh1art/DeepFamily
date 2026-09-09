import type { EnvironmentSummary, RunState } from "./types";

const apiOrigin = (import.meta.env.VITE_API_ORIGIN as string | undefined)?.replace(/\/$/, "") ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiOrigin}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch {
      // Preserve the HTTP status when a proxy returns a non-JSON error page.
    }
    throw new Error(detail);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function getEnvironment(): Promise<EnvironmentSummary> {
  return request<EnvironmentSummary>("/api/v1/environments/current");
}

export function createRun(question: string): Promise<RunState> {
  return request<RunState>("/api/v1/runs?background=true", {
    method: "POST",
    body: JSON.stringify({ question }),
  });
}

export function getRun(runId: string): Promise<RunState> {
  return request<RunState>(`/api/v1/runs/${encodeURIComponent(runId)}`);
}

export function deleteRun(runId: string): Promise<void> {
  return request<void>(`/api/v1/runs/${encodeURIComponent(runId)}`, {
    method: "DELETE",
  });
}
