import axios from "axios";

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000",
  timeout: 120000
});

export type Authority = {
  authority_id: string;
  authority_name: string;
  department: string;
  email: string;
  created_at: string;
  status: string;
};

export type PublicKey = {
  key_id: string;
  authority_id: string;
  authority_name: string;
  public_key_pem: string;
  algorithm: string;
  key_size: number;
  created_at: string;
  active: boolean;
  fingerprint_sha256: string;
};

export type SignedDocument = {
  document_id: string;
  authority_id: string;
  authority_name: string;
  public_key_id?: string;
  key_id: string;
  original_filename: string;
  signed_filename?: string;
  file_type: string;
  storage_type?: string;
  download_url?: string;
  signed_file_download_url: string;
  signed_file_storage_path: string;
  created_at: string;
  signature_status?: string;
  status: string;
};

export type AuditLog = {
  event_type: string;
  actor?: string;
  authority_id?: string;
  key_id?: string;
  document_id?: string;
  timestamp: string;
  details?: Record<string, unknown>;
  previous_hash?: string;
  current_hash?: string;
};
