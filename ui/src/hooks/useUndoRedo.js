import { useState, useCallback, useRef } from "react";

/**
 * Custom hook for undo/redo functionality
 * @param {any} initialValue - Initial state value
 * @param {number} maxHistory - Maximum history size (default: 50)
 * @returns {Object} - { value, setValue, undo, redo, canUndo, canRedo, clearHistory }
 */
export const useUndoRedo = (initialValue, maxHistory = 50) => {
  const [value, setValueState] = useState(initialValue);
  const historyRef = useRef([initialValue]);
  const currentIndexRef = useRef(0);

  const setValue = useCallback(
    (newValue) => {
      const currentValue =
        typeof newValue === "function" ? newValue(historyRef.current[currentIndexRef.current]) : newValue;

      // Remove any history after current index (when we're not at the end)
      if (currentIndexRef.current < historyRef.current.length - 1) {
        historyRef.current = historyRef.current.slice(0, currentIndexRef.current + 1);
      }

      // Add new value to history
      historyRef.current.push(currentValue);

      // Limit history size
      if (historyRef.current.length > maxHistory) {
        historyRef.current.shift();
      } else {
        currentIndexRef.current = historyRef.current.length - 1;
      }

      setValueState(currentValue);
    },
    [maxHistory]
  );

  const undo = useCallback(() => {
    if (currentIndexRef.current > 0) {
      currentIndexRef.current -= 1;
      setValueState(historyRef.current[currentIndexRef.current]);
    }
  }, []);

  const redo = useCallback(() => {
    if (currentIndexRef.current < historyRef.current.length - 1) {
      currentIndexRef.current += 1;
      setValueState(historyRef.current[currentIndexRef.current]);
    }
  }, []);

  const canUndo = currentIndexRef.current > 0;
  const canRedo = currentIndexRef.current < historyRef.current.length - 1;

  const clearHistory = useCallback(() => {
    const currentValue = historyRef.current[currentIndexRef.current];
    historyRef.current = [currentValue];
    currentIndexRef.current = 0;
  }, []);

  return {
    value,
    setValue,
    undo,
    redo,
    canUndo,
    canRedo,
    clearHistory,
  };
};

export default useUndoRedo;

