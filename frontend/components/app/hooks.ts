"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type Loadable<T> = {
  data: T | null;
  error: unknown;
  loading: boolean;
  reload: () => void;
};

/** Loads data on mount and on reload(). Setters only run after an await. */
export function useLoad<T>(fn: () => Promise<T>): Loadable<T> {
  const [state, setState] = useState<{ data: T | null; error: unknown; loading: boolean }>({
    data: null, error: null, loading: true,
  });
  const fnRef = useRef(fn);
  useEffect(() => { fnRef.current = fn; });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fnRef.current()
      .then((data) => !cancelled && setState({ data, error: null, loading: false }))
      .catch((error) => !cancelled && setState((s) => ({ ...s, error, loading: false })));
    return () => { cancelled = true; };
  }, [tick]);

  const reload = useCallback(() => {
    setState((s) => ({ ...s, loading: true, error: null }));
    setTick((t) => t + 1);
  }, []);
  return { ...state, reload };
}
