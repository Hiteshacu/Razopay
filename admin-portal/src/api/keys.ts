import { apiClient, Authority, PublicKey } from "./client";

export async function listAuthorities() {
  const { data } = await apiClient.get<Authority[]>("/api/authorities");
  return data;
}

export async function createAuthority(payload: {
  authority_name: string;
  department: string;
  email: string;
}) {
  const { data } = await apiClient.post<Authority>("/api/authorities", payload);
  return data;
}

export async function listPublicKeys(authorityId?: string) {
  const { data } = await apiClient.get<PublicKey[]>("/api/keys/public", {
    params: authorityId ? { authority_id: authorityId } : undefined
  });
  return data;
}

export async function generatePublicKey(authorityId: string, authorityName?: string) {
  const { data } = await apiClient.post<PublicKey>("/api/keys/generate", {
    authority_id: authorityId,
    authority_name: authorityName
  });
  return data;
}

