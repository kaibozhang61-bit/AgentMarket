import { useCallback, useEffect, useRef } from "react";

/**
 * Debounced auto-save hook.
 * Calls `saveFn` after `delayMs` of inactivity since the last `trigger()`.
 */
export function useAutoSave(
  saveFn: () => Promise<void>,
  delayMs = 1500,
) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const saveFnRef = useRef(saveFn);
  saveFnRef.current = saveFn;

  const trigger = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      saveFnRef.current().catch(console.error);
    }, delayMs);
  }, [delayMs]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  return trigger;
}
