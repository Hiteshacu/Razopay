import { FileSignature, KeyRound, LayoutDashboard, ListChecks, ScrollText, ShieldCheck, UserCheck, Users2 } from "lucide-react";
import type { ComponentType } from "react";

type View = "dashboard" | "authorities" | "keys" | "sign" | "documents" | "audit" | "approvals" | "users";

type Role = "owner" | "admin" | "member";

const items: Array<{ id: View; label: string; icon: ComponentType<{ size?: number }>; adminOnly?: boolean }> = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "authorities", label: "Authorities", icon: ShieldCheck },
  { id: "keys", label: "Keys", icon: KeyRound },
  { id: "sign", label: "Sign", icon: FileSignature },
  { id: "documents", label: "Documents", icon: ListChecks },
  { id: "audit", label: "Audit", icon: ScrollText },
  { id: "approvals", label: "Approvals", icon: UserCheck, adminOnly: true },
  { id: "users", label: "People", icon: Users2, adminOnly: true }
];

export function Navbar({
  view,
  onChange,
  email,
  role = "member",
  onSignOut
}: {
  view: View;
  onChange: (view: View) => void;
  email?: string | null;
  role?: Role;
  onSignOut?: () => void;
}) {
  const administers = role === "owner" || role === "admin";
  const visible = items.filter((item) => !item.adminOnly || administers);
  return (
    <aside className="sidebar">
      <div className="brand-mark">DTS</div>
      <div>
        <p className="eyebrow">Digital Trust Shield</p>
        <h1>Authority Console</h1>
      </div>
      <nav>
        {visible.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              className={view === item.id ? "nav-item active" : "nav-item"}
              onClick={() => onChange(item.id)}
            >
              <Icon size={18} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>
      {onSignOut && (
        // Shown whenever a sign-out is possible, not only when the address is
        // known. With authentication disabled the backend reports no email,
        // and gating the whole block on it left the console with no way out.
        <div className="signed-in-as">
          <span>{email ? "Signed in as" : "Signed in"}</span>
          {email && <strong>{email}</strong>}
          <span className={`role-pill role-${role}`}>{role}</span>
          <button type="button" onClick={onSignOut}>
            Sign out
          </button>
        </div>
      )}
      <p className="security-note">
        Private keys stay encrypted on the backend. Firebase stores public proof metadata only.
      </p>
    </aside>
  );
}

export type { View, Role };
