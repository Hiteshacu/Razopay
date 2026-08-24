import { apiClient } from "./client";

export async function login(username: string, password: string) {
  const { data } = await apiClient.post("/api/auth/login", { username, password });
  return data as { success: boolean; token: string; message: string };
}

