import { useCallback, useEffect, useRef, useState } from "react";

// A screen that follows something in progress, such as a dataset build: read on opening, then
// asked again `everyMs` after each answer while `again(answer)` holds, and whenever the
// developer comes back to the tab. Never a new request before the last is answered, and quiet
// once nothing is in progress, so an open tab doesn't keep the database busy. `reload` asks now.
export function usePoll<T>(
  read: () => Promise<T>,
  everyMs: number,
  again: (answer: T) => boolean,
): { data: T | null; error: string | null; reload: () => void } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useRef<() => void>(() => undefined);
  const keepGoing = useRef(again);
  keepGoing.current = again;

  useEffect(() => {
    let stopped = false;
    let asking = false;
    let timer: number | undefined;

    async function ask() {
      if (asking) return;
      asking = true;
      window.clearTimeout(timer);
      let more = true;
      try {
        const answer = await read();
        if (stopped) return;
        setData(answer);
        setError(null);
        more = keepGoing.current(answer);
      } catch (problem) {
        if (stopped) return;
        setError(problem instanceof Error ? problem.message : String(problem));
      } finally {
        asking = false;
      }
      if (more && !stopped) timer = window.setTimeout(() => void ask(), everyMs);
    }

    load.current = () => void ask();
    const onReturn = () => void ask();
    window.addEventListener("focus", onReturn);
    void ask();
    return () => {
      stopped = true;
      window.removeEventListener("focus", onReturn);
      window.clearTimeout(timer);
    };
  }, [read, everyMs]);

  const reload = useCallback(() => load.current(), []);
  return { data, error, reload };
}
