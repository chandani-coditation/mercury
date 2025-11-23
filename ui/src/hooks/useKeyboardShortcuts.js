import { useEffect } from "react";

/**
 * Custom hook for keyboard shortcuts
 * @param {Object} shortcuts - Map of key combinations to handler functions
 * @param {boolean} enabled - Whether shortcuts are enabled
 * 
 * @example
 * useKeyboardShortcuts({
 *   'ctrl+k': () => console.log('Search'),
 *   'escape': () => closeModal(),
 *   'n': () => openNewTriage(), // when meta key is pressed
 * }, true);
 */
export const useKeyboardShortcuts = (shortcuts = {}, enabled = true) => {
  useEffect(() => {
    if (!enabled || Object.keys(shortcuts).length === 0) return;

    const handleKeyDown = (event) => {
      const key = event.key.toLowerCase();
      const ctrl = event.ctrlKey || event.metaKey;
      const shift = event.shiftKey;
      const alt = event.altKey;

      // Build key combination string
      const parts = [];
      if (ctrl) parts.push("ctrl");
      if (shift) parts.push("shift");
      if (alt) parts.push("alt");
      parts.push(key);

      const combination = parts.join("+");

      // Check for exact match first
      if (shortcuts[combination]) {
        event.preventDefault();
        shortcuts[combination](event);
        return;
      }

      // Check for key-only match (when no modifiers)
      if (!ctrl && !shift && !alt && shortcuts[key]) {
        event.preventDefault();
        shortcuts[key](event);
        return;
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [shortcuts, enabled]);
};

export default useKeyboardShortcuts;

