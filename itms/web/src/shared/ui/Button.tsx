import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

import { cn } from "@/shared/lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-[rgb(var(--accent))] text-white border border-transparent hover:opacity-90 disabled:opacity-50",
  secondary:
    "surface text-app hover:bg-[rgb(var(--surface-muted))] disabled:opacity-50",
  ghost:
    "bg-transparent border border-transparent text-muted hover:bg-[rgb(var(--surface-muted))] hover:text-app disabled:opacity-50",
  danger:
    "bg-[rgb(var(--danger))] text-white border border-transparent hover:opacity-90 disabled:opacity-50",
};

const SIZES: Record<Size, string> = {
  sm: "h-7 px-2 text-xs gap-1.5",
  md: "h-8 px-3 gap-2",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  icon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", icon, className, children, type = "button", ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cn(
        "inline-flex items-center justify-center rounded-md font-medium whitespace-nowrap transition-colors",
        "disabled:cursor-not-allowed",
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...rest}
    >
      {icon}
      {children}
    </button>
  );
});

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  label: string;
}

export function IconButton({ label, className, children, ...rest }: IconButtonProps) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={cn(
        "inline-flex h-7 w-7 items-center justify-center rounded-md text-muted transition-colors",
        "hover:bg-[rgb(var(--surface-muted))] hover:text-app disabled:opacity-50",
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}
