export type Decision = "ALLOW" | "REVIEW" | "BLOCK";

export type Transaction = {
  transaction_id: string;
  decision_id: string;
  timestamp: string;
  amount_minor: number;
  currency: string;
  amount: number;
  merchant_id: string;
  merchant_category: string;
  risk_probability: number;
  decision: Decision;
  policy_version: string;
  model_version: string;
  latency_ms: number;
  state_update_status: "pending" | "processing" | "applied" | "already_applied" | "retrying" | "dead_letter";
  explanations: Array<{ label: string; direction: string; contribution: number }>;
  features: Record<string, number>;
};

export type CaseSummary = {
  case_id: string;
  queue: string;
  priority: string;
  status: string;
  assigned_to: string | null;
  opened_at: string;
  transaction: Transaction;
};

export type ApiProblem = {
  code?: string;
  title?: string;
  detail?: string;
  request_id?: string;
  retryable?: boolean;
};

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly problem: ApiProblem,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type ApiOptions = RequestInit & { timeoutMs?: number };

/** Browser calls stay same-origin; the Next route handler is the API boundary. */
export async function api<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), options.timeoutMs ?? 12_000);
  try {
    const response = await fetch(path, {
      ...options,
      signal: options.signal ?? controller.signal,
      cache: "no-store",
      headers: { "Content-Type": "application/json", ...(options.headers ?? {}) },
    });
    if (!response.ok) {
      const problem = (await response.json().catch(() => ({}))) as ApiProblem;
      throw new ApiError(problem.detail ?? `Request failed (${response.status})`, response.status, problem);
    }
    return (await response.json()) as T;
  } finally {
    window.clearTimeout(timeout);
  }
}

export function formatMoney(amountMinor: number, currency = "USD"): string {
  return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(amountMinor / 100);
}
