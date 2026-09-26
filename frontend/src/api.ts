export type ApiError = {
  code: string;
  message: string;
  request_id?: string;
  details?: unknown;
};
export type Scope = {
  id: number;
  name: string;
  cidr: string;
  enabled: boolean;
  approved_at: string;
  max_concurrency: number;
  connect_timeout_ms: number;
  ports: number[];
};

function csrfToken(): string {
  const entry = document.cookie
    .split("; ")
    .find((part) => part.startsWith("netsentinel_csrf="));
  return entry
    ? decodeURIComponent(entry.slice("netsentinel_csrf=".length))
    : "";
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const method = options.method ?? "GET";
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    credentials: "same-origin",
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(method !== "GET" ? { "X-CSRF-Token": csrfToken() } : {}),
      ...options.headers,
    },
  });
  const data = await response.json();
  if (!response.ok) throw data as ApiError;
  return data as T;
}
