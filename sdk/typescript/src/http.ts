/**
 * HTTP utilities: fetch wrapper, error parsing, response unwrapping.
 */

import {
  VectorDBError,
  NotFoundError,
  AlreadyExistsError,
  DimensionMismatchError,
  AuthenticationError,
  RateLimitError,
  ValidationError,
} from "./errors.js";
import type { ApiResponse } from "./types.js";

const STATUS_MAP: Record<number, new (msg: string, code: number) => VectorDBError> = {
  401: AuthenticationError,
  403: AuthenticationError,
  404: NotFoundError,
  409: AlreadyExistsError,
  422: ValidationError,
  429: RateLimitError,
};

export function raiseForResponse(code: number, message: string): never {
  if (code === 400 && message.toLowerCase().includes("dimension")) {
    throw new DimensionMismatchError(message, code);
  }
  const Cls = STATUS_MAP[code];
  if (Cls) throw new Cls(message, code);
  throw new VectorDBError(message, code);
}

export function unwrap<T>(body: ApiResponse<T>): T {
  if (body.status === "error") {
    const err = body.error ?? { code: 0, message: "Unknown error" };
    raiseForResponse(err.code, err.message);
  }
  return body.data as T;
}

export type FetchFn = (url: string, init?: RequestInit) => Promise<Response>;

export class HttpClient {
  private readonly baseUrl: string;
  private readonly headers: Record<string, string>;
  private readonly fetchFn: FetchFn;

  constructor(baseUrl: string, apiKey: string, fetchFn?: FetchFn) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.headers = {
      "x-api-key": apiKey,
      "Content-Type": "application/json",
      Accept: "application/json",
    };
    this.fetchFn = fetchFn ?? (globalThis.fetch as FetchFn);
  }

  async request<T>(
    method: string,
    path: string,
    options: { body?: unknown; params?: Record<string, string> } = {}
  ): Promise<T> {
    let url = `${this.baseUrl}${path}`;
    if (options.params && Object.keys(options.params).length > 0) {
      const qs = new URLSearchParams(options.params).toString();
      url = `${url}?${qs}`;
    }

    const init: RequestInit = {
      method,
      headers: this.headers,
    };
    if (options.body !== undefined) {
      init.body = JSON.stringify(options.body);
    }

    const resp = await this.fetchFn(url, init);
    const body = (await resp.json()) as ApiResponse<T>;

    if (!resp.ok) {
      // HTTP-level failure (e.g. 401 from middleware)
      const msg = body?.error?.message ?? `HTTP ${resp.status}`;
      raiseForResponse(resp.status, msg);
    }

    return unwrap(body);
  }

  /**
   * Send a multipart/form-data POST request (used for file uploads).
   *
   * @param path - API endpoint path.
   * @param fields - Plain text form fields (key-value pairs).
   * @param file - The file content as a Blob or Buffer.
   * @param filename - The filename to attach.
   */
  async requestMultipart<T>(
    path: string,
    fields: Record<string, string>,
    file: Blob | Buffer,
    filename: string
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;

    const formData = new FormData();
    for (const [key, value] of Object.entries(fields)) {
      formData.append(key, value);
    }
    // Convert Buffer to Blob if needed (Node.js compatibility)
    const blob =
      file instanceof Blob ? file : new Blob([file], { type: "text/plain" });
    formData.append("file", blob, filename);

    // Use all headers except Content-Type — the browser/runtime sets the
    // correct multipart boundary automatically.
    const { "Content-Type": _, ...headersWithoutCT } = this.headers;

    const init: RequestInit = {
      method: "POST",
      headers: headersWithoutCT,
      body: formData,
    };

    const resp = await this.fetchFn(url, init);
    const body = (await resp.json()) as ApiResponse<T>;

    if (!resp.ok) {
      const msg = body?.error?.message ?? `HTTP ${resp.status}`;
      raiseForResponse(resp.status, msg);
    }

    return unwrap(body);
  }
}
