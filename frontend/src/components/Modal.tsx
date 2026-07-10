import { useEffect, type ReactNode } from "react";

/** A centred modal over a click-to-dismiss backdrop; Escape also closes it. */
export function Modal({
  title,
  icon,
  sub,
  onClose,
  children,
  footer,
}: {
  title: ReactNode;
  icon?: ReactNode;
  sub?: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true">
        <h3 className="modal-title">
          {icon}
          {title}
        </h3>
        {sub != null && <p className="sub">{sub}</p>}
        {children}
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  );
}
