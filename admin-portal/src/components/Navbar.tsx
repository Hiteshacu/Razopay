import { FileSignature, KeyRound, LayoutDashboard, ListChecks, ScrollText, ShieldCheck, UserCheck, Users2 } from "lucide-react";
import { motion } from "motion/react";
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

function NavButton({
  item,
  active,
  onSelect
}: {
  item: { id: View; label: string; icon: ComponentType<{ size?: number }> };
  active: boolean;
  onSelect: (view: View) => void;
}) {
  const Icon = item.icon;
  return (
    <button
      className={active ? "nav-item active" : "nav-item"}
      onClick={() => onSelect(item.id)}
      aria-current={active ? "page" : undefined}
    >
      {/* One highlight shared across every item by layoutId, so changing
          page slides it rather than fading one out and another in. */}
      {active && (
        <motion.span
          layoutId="nav-pill"
          className="nav-pill"
          transition={{ type: "spring", stiffness: 420, damping: 34 }}
        />
      )}
      <Icon size={17} />
      <span>{item.label}</span>
    </button>
  );
}

export function Navbar({
  view,
  onChange,
  email,
  role,
  onSignOut
}: {
  view: View;
  onChange: (view: View) => void;
  email?: string | null;
  // Required on purpose. This defaulted to "member", so when a caller forgot
  // to pass it the sidebar quietly hid every administrator control and
  // reported the wrong role — with nothing failing to point at the cause.
  role: Role;
  onSignOut?: () => void;
}) {
  const administers = role === "owner" || role === "admin";
  const workspace = items.filter((item) => !item.adminOnly);
  const administration = administers ? items.filter((item) => item.adminOnly) : [];
  return (
    <aside className="sidebar">
      <div className="brand-mark">DTS</div>
      <div>
        <p className="eyebrow">Digital Trust Shield</p>
        <h1>Authority Console</h1>
      </div>
      <nav>
        {workspace.map((item) => (
          <NavButton key={item.id} item={item} active={view === item.id} onSelect={onChange} />
        ))}

        {administration.length > 0 && (
          <>
            <p className="nav-section">Administration</p>
            {administration.map((item) => (
              <NavButton key={item.id} item={item} active={view === item.id} onSelect={onChange} />
            ))}
          </>
        )}
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
