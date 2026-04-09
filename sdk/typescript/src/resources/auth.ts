/**
 * Auth resource — user registration and login (no API key required).
 */
import type { HttpClient } from "../http.js";

export interface AuthResponse {
  user: {
    id: number;
    email: string;
    created_at: string;
  };
  api_key: {
    id: number;
    key: string;
    name: string;
    role: string;
  };
}

export class AuthResource {
  constructor(private readonly http: HttpClient) {}

  /** Register a new user. Returns user info and an admin API key. */
  async register(email: string, password: string): Promise<AuthResponse> {
    return this.http.request("POST", "/v1/auth/register", {
      body: { email, password },
    });
  }

  /** Login an existing user. Returns user info and an admin API key. */
  async login(email: string, password: string): Promise<AuthResponse> {
    return this.http.request("POST", "/v1/auth/login", {
      body: { email, password },
    });
  }
}
