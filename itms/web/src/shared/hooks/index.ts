import { useEffect, useRef, useState } from "react";

export function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

interface HotkeyOptions {
  ctrl?: boolean;
  shift?: boolean;
  /** Внутри полей ввода горячие клавиши по умолчанию не срабатывают. */
  allowInInput?: boolean;
}

export function useHotkey(key: string, handler: () => void, options: HotkeyOptions = {}): void {
  const callback = useRef(handler);
  callback.current = handler;

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() !== key.toLowerCase()) return;
      if (!!options.ctrl !== (event.ctrlKey || event.metaKey)) return;
      if (!!options.shift !== event.shiftKey) return;
      if (!options.allowInInput) {
        const target = event.target as HTMLElement | null;
        const tag = target?.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target?.isContentEditable) {
          return;
        }
      }
      event.preventDefault();
      callback.current();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [key, options.ctrl, options.shift, options.allowInInput]);
}
