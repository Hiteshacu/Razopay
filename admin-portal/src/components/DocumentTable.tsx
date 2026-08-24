import { SignedDocument } from "../api/client";

export function DocumentTable({ documents }: { documents: SignedDocument[] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Document</th>
            <th>Authority</th>
            <th>Key</th>
            <th>Signed At</th>
            <th>Output</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((document) => (
            <tr key={document.document_id}>
              <td>{document.original_filename}</td>
              <td>{document.authority_name}</td>
              <td>{document.key_id}</td>
              <td>{new Date(document.created_at).toLocaleString()}</td>
              <td>
                <a
                  href={document.download_url ?? document.signed_file_download_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  Download
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
