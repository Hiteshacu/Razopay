import { apiClient } from "./client";

export async function signDocument(file: File, authorityId: string, keyId: string) {
  const form = new FormData();
  form.append("file", file);
  form.append("authority_id", authorityId);
  form.append("key_id", keyId);
  const { data } = await apiClient.post("/api/sign", form, {
    headers: { "Content-Type": "multipart/form-data" }
  });
  return data as {
    success: boolean;
    document_id: string;
    signed_file_url: string;
    download_url: string;
    signed_file_storage_path: string;
    signed_filename: string;
    storage_type: string;
    key_id: string;
    authority_id: string;
    message: string;
  };
}
