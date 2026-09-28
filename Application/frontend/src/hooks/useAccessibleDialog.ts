import { useEffect, useRef } from "react";

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled]):not([type=hidden])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");
const openDialogStack: HTMLElement[] = [];

export function useAccessibleDialog<T extends HTMLElement>(
  isOpen: boolean,
  onClose: () => void,
  closeOnEscape = true,
) {
  const dialogRef = useRef<T>(null);
  const closeRef = useRef(onClose);
  const closeOnEscapeRef = useRef(closeOnEscape);
  closeRef.current = onClose;
  closeOnEscapeRef.current = closeOnEscape;

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!isOpen || !dialog) return;

    const previousFocus = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    openDialogStack.push(dialog);

    const focusables = () => Array.from(
      dialog.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
    ).filter((element) => element.getAttribute("aria-hidden") !== "true" && element.getClientRects().length > 0);

    const firstFocus = focusables()[0] ?? dialog;
    const focusFrame = window.requestAnimationFrame(() => firstFocus.focus());

    const handleKeyDown = (event: KeyboardEvent) => {
      if (openDialogStack[openDialogStack.length - 1] !== dialog) return;
      if (event.key === "Escape") {
        if (closeOnEscapeRef.current) {
          event.preventDefault();
          event.stopPropagation();
          closeRef.current();
        }
        return;
      }

      if (event.key !== "Tab") return;
      const items = focusables();
      if (items.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }

      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      window.removeEventListener("keydown", handleKeyDown);
      const stackIndex = openDialogStack.lastIndexOf(dialog);
      if (stackIndex !== -1) openDialogStack.splice(stackIndex, 1);
      document.body.style.overflow = previousOverflow;
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, [isOpen]);

  return dialogRef;
}
