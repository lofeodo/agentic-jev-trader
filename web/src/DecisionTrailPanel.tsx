// The decision trail side panel (spec appendix 7, section 6): opened by a click on a trade, an
// open position or a decision, it shows everything asked and answered on the way to it, as a
// strip of boxes, one per stop. Skeleton: a placeholder body that lists the stops.
import { useCallback } from "react";

import { fetchTrail, type DecisionTrail } from "./api/client";
import { AssetTag, ErrorBox, SidePanel } from "./pieces";
import { useRead } from "./useRead";

export function DecisionTrailPanel({ simId, decision, onClose }: { simId: number; decision: string; onClose: () => void }) {
  const read = useCallback(() => fetchTrail(simId, decision), [simId, decision]);
  const { data: trail, error } = useRead(read);

  return (
    <SidePanel title="Decision trail" wide onClose={onClose}>
      {error && <ErrorBox title="Cannot read this decision trail" text={error} />}
      {!trail && !error && <p className="font-mono text-dim">Loading...</p>}
      {trail && <TrailBody trail={trail} />}
    </SidePanel>
  );
}

function TrailBody({ trail }: { trail: DecisionTrail }) {
  return (
    <>
      <h2 className="mb-1 text-[1.4rem] leading-tight">
        <AssetTag asset={trail.asset} /> {trail.kind.replaceAll("_", " ")}
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
