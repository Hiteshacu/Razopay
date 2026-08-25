import { FileSignature, KeyRound, LayoutDashboard, ListChecks, ScrollText, ShieldCheck } from "lucide-react";
import type { ComponentType } from "react";

type View = "dashboard" | "authorities" | "keys" | "sign" | "documents" | "audit";

const items: Array<{ id: View; label: string; icon: ComponentType<{ size?: number }> }> = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "authorities", label: "Authorities", icon: ShieldCheck },
  { id: "keys", label: "Keys", icon: KeyRound },
  { id: "sign", label: "Sign", icon: FileSignature },
  { id: "documents", label: "Documents", icon: ListChecks },
  { id: "audit", label: "Audit", icon: ScrollText }
];

export function Navbar({
  view,
  onChange,
  email,
  onSignOut
}: {
  view: View;
  onChange: (view: View) => void;
  email?: string | null;
  onSignOut?: () => void;
}) {
  return (
    <aside className="sidebar">
      <div className="brand-mark">DTS</div>
      <div>
        <p className="eyebrow">Digital Trust Shield</p>
        <h1>Authority Console</h1>
      </div>
      <nav>
        {items.map((item) => {
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
      {email && (
        <div className="signed-in-as">
          <span>Signed in as</span>
          <strong>{email}</strong>
          {onSignOut && (
            <button type="button" onClick={onSignOut}>
              Sign out
            </button>
          )}
        </div>
      )}
      <p className="security-note">
        Private keys stay encrypted on the backend. Firebase stores public proof metadata only.
      </p>
    </aside>
  );
}

export type { View };
