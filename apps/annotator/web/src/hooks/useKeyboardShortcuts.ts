import { useEffect } from "react";

interface ShortcutHandlers {
  onPlayPause: () => void;
  onPrev: () => void;
  onNext: () => void;
  onValidate: () => void;
  onSave: () => void;
  onDeselect?: () => void;
}

export function useKeyboardShortcuts(handlers: ShortcutHandlers, enabled = true) {
  useEffect(() => {
    if (!enabled) return;

    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const isInput =
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.tagName === "SELECT";

      if ((e.metaKey || e.ctrlKey) && e.key === "s") {
        e.preventDefault();
        handlers.onSave();
        return;
      }

      if (isInput && e.key !== "Enter") return;

      switch (e.key) {
        case " ":
          e.preventDefault();
          handlers.onPlayPause();
          break;
        case "ArrowUp":
        case "k":
        case "K":
          e.preventDefault();
          handlers.onPrev();
          break;
        case "ArrowDown":
        case "j":
        case "J":
          e.preventDefault();
          handlers.onNext();
          break;
        case "Enter":
          if (!e.shiftKey) {
            e.preventDefault();
            handlers.onValidate();
          }
          break;
        case "Escape":
          e.preventDefault();
          handlers.onDeselect?.();
          break;
        default:
          break;
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [enabled, handlers]);
}
