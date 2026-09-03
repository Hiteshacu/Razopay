/**
 * Where the API lives, normalised.
 *
 * `VITE_API_BASE_URL` is typed into a hosting dashboard by hand, and the most
 * common way to get it wrong is to paste the host without a scheme —
 * `p01--foo--bar.code.run` instead of `https://p01--foo--bar.code.run`. axios
 * treats a value with no scheme as a *relative* path, so every request quietly
 * goes to `https://<the-portal>/p01--foo--bar.code.run/api/...` and comes back
 * 404. Nothing throws; the console shows a not-found for a URL nobody wrote.
 *
 * So a missing scheme is repaired here rather than trusted. A host that is
 * plainly local keeps http, because https on localhost fails the handshake;
 * everything else gets https, because a deployed API on plain http would be
 * blocked as mixed content anyway.
 */
export function apiBaseUrl(): string {
  const raw = (import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000").trim();
  if (!raw) return "http://127.0.0.1:8000";

  const withScheme = /^https?:\/\//i.test(raw)
    ? raw
    : `${/^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/i.test(raw) ? "http" : "https"}://${raw}`;

  return withScheme.replace(/\/+$/, "");
}
