import { CheckCircle2, XCircle } from "lucide-react";
import type { ReactNode } from "react";

export function ResultCard({
  title,
  tone,
  children
}: {
  title: string;
  tone: "success" | "danger" | "neutral";
  children: ReactNode;
}) {
  const Icon = tone === "danger" ? XCircle : CheckCircle2;
  return (
    <section className={`result-card ${tone}`}>
      <Icon size={24} />
      <div>
        <h3>{title}</h3>
        <div>{children}</div>
      </div>
    </section>
  );
}
