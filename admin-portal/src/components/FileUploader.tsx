import { UploadCloud } from "lucide-react";

export function FileUploader({ file, onFile }: { file: File | null; onFile: (file: File | null) => void }) {
  return (
    <label className="upload-box">
      <UploadCloud size={28} />
      <span>{file ? file.name : "Drop or select a poster/PDF"}</span>
      <small>PNG, JPG, JPEG, or PDF</small>
      <input
        type="file"
        accept=".png,.jpg,.jpeg,.pdf"
        onChange={(event) => onFile(event.target.files?.[0] ?? null)}
      />
    </label>
  );
}

