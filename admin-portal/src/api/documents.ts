import { apiClient, AuditLog, SignedDocument } from "./client";

export async function listDocuments() {
  const { data } = await apiClient.get<SignedDocument[]>("/api/documents");
  return data;
}

export async function listAuditLogs() {
  const { data } = await apiClient.get<AuditLog[]>("/api/audit");
  return data;
}

