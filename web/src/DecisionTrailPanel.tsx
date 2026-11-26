// The decision trail side panel (spec appendix 7, section 6): opened by a click on a trade, an
// open position or a decision, it shows everything asked and answered on the way to it, as a
// strip of boxes, one per stop. Skeleton: a placeholder body that lists the stops.
import { useCallback, useEffect } from "react";

import { fetchTrail, type DecisionTrail } from "./api/client";
import { AssetTag, ErrorBox } from "./pieces";
import { useRead } from "./useRead";

export function DecisionTrailPanel({ simId, decision, onClose }: { simId: number; decision: string; onClose: () => void }) {
  const read = useCallback(() => fetchTrail(simId, decision), [simId, decision]);
  const { data: trail, error } = useRead(read);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <aside
      aria-label="Decision trail"
      className="fixed top-0 right-0 bottom-0 z-30 w-[min(720px,100vw)] overflow-y-auto border-l-[1.5px] border-rule bg-screen"
    >
      <div className="flex items-center justify-between bg-amber px-[2ch] py-1 font-mono text-[13.5px] tracking-widest text-screen">
        <span>Decision trail</span>
        <button type="button" onClick={onClose} className="cursor-pointer font-mono tracking-widest uppercase" aria-label="Close the decision trail">
          Close [Esc]
        </button>
      </div>
      <div className="px-[2ch] py-4">
        {error && <ErrorBox title="Cannot read this decision trail" text={error} />}
        {!trail && !error && <p className="font-mono text-dim">Loading...</p>}
        {trail && <TrailBody trail={trail} />}
      </div>
    </aside>
  );
}

function TrailBody({ trail }: { trail: DecisionTrail }) {
  return (
    <>
      <h2 className="mb-1 text-[1.4rem] leading-tight">
        <AssetTag asset={trail.asset} /> {trail.kind}
      </h2>
      <p className="mb-4 font-mono text-[12.5px] tracking-wider text-dim">Decision {trail.decision}</p>
      <ol className="flex flex-wrap gap-2 font-mono text-[13.5px] tracking-wider">
        {trail.stops.map((stop) => (
          <li key={stop.name} className="border-[1.5px] border-rule px-[1.5ch] py-1">
            <div>{stop.name}</div>
            <div className="text-dim">{stop.outcome}</div>
          </li>
        ))}
      </ol>
    </>
  );
}
