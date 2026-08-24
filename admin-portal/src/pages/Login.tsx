import { ShieldCheck } from "lucide-react";
import type { FormEvent } from "react";
import { useState } from "react";
import { login } from "../api/auth";

export function Login({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("admin123");
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const response = await login(username, password);
      localStorage.setItem("dts_admin_token", response.token);
      onLogin();
    } catch (exc) {
      setError("Invalid admin credentials or backend unavailable.");
    }
  }

  return (
    <main className="login-shell">
      <section className="login-panel">
        <div className="login-icon">
          <ShieldCheck size={34} />
        </div>
        <p className="eyebrow">Digital Trust Shield</p>
        <h1>Authority signing console</h1>
        <form onSubmit={handleSubmit}>
          <label>
            Username
            <input value={username} onChange={(event) => setUsername(event.target.value)} />
          </label>
          <label>
            Password
            <input value={password} type="password" onChange={(event) => setPassword(event.target.value)} />
          </label>
          {error && <p className="error-text">{error}</p>}
          <button className="primary-button" type="submit">Enter console</button>
        </form>
      </section>
    </main>
  );
}
