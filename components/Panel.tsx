import { ReactNode } from "react";

export function Panel({
  title,
  subtitle,
  children,
  right,
  className = "",
}: {
  title?: string;
  subtitle?: string;
  children: ReactNode;
  right?: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-xl border border-border bg-panel p-5 ${className}`}
    >
      {(title || right) && (
        <header className="mb-3 flex items-baseline justify-between">
          <div>
            {title && (
              <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">
                {title}
              </h2>
            )}
            {subtitle && <p className="text-xs text-muted">{subtitle}</p>}
          </div>
          {right}
        </header>
      )}
      {children}
    </section>
  );
}
