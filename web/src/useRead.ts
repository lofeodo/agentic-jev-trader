import { useEffect, useState } from "react";

// A screen that changes slowly: read on opening and whenever the developer comes back to the
// tab, never sending a new request before the last is answered. No timer, so an open tab
// doesn't keep the database busy.
export function useRead<T>(read: () => Promise<T>): { data: T | null; error: string | null } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let stopped = false;
    let asking = false;
    async function load() {
      if (asking) return;
      asking = true;
      try {
        const answer = await read();
        if (stopped) return;
        setData(answer);
        setError(null);
      } catch (problem) {
        if (!stopped) setError(problem instanceof Error ? problem.message : String(problem));
      } finally {
        asking = false;
      }
    }
    const onReturn = () => void load();
    window.addEventListener("focus", onReturn);
    void load();
    return () => {
      stopped = true;
      window.removeEventListener("focus", onReturn);
    };
  }, [read]);

  return { data, error };
}
