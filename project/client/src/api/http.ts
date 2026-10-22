// Fetch wrapper: JSON in and out, RFC 9457 problem details turned into a typed error.

export class ApiError extends Error {
  readonly status: number;
  readonly type: string;
  readonly title: string;
  readonly detail?: string;
  readonly body: Record<string, unknown>;

  constructor(status: number, body: Record<string, unknown>) {
    const title = typeof body.title === "string" ? body.title : `HTTP ${status}`;
    const detail = typeof body.detail === "string" ? body.detail : undefined;
    super(detail ? `${title}: ${detail}` : title);
    this.status = status;
    this.type = typeof body.type === "string" ? body.type : "about:blank";
    this.title = title;
    this.detail = detail;
    this.body = body;
  }

  /** The stable part of a problem type, e.g. "paid-models-not-confirmed". */
  get code(): string {
    return this.type.replace("urn:edugen:problem:", "");
  }
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  token?: string | null;
  headers?: Record<string, string>;
}

export async function request<T>(url: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", ...options.headers };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (options.token) headers.Authorization = `Bearer ${options.token}`;

  let response: Response;
  try {
    response = await fetch(url, {
      method: options.method ?? "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch {
    throw new ApiError(0, { title: "Network error", detail: "The server could not be reached." });
  }

  const text = await response.text();
  const data = text ? safeJson(text) : {};
  if (!response.ok) throw new ApiError(response.status, data as Record<string, unknown>);
  return data as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return { title: "Unexpected response", detail: text.slice(0, 200) };
  }
}
