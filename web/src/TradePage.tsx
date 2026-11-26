// The Trade page (spec appendix 7, section 7): one trade reviewed the way a trader would. The
// price chart around it, the order, every position review, the nightly charges, and memory.
// Clicking a review opens its decision trail. Skeleton: a placeholder body.
import { useCallback, useState } from "react";

import { fetchTrade, type TradePage as TradePageAnswer } from "./api/client";
import { DecisionTrailPanel } from "./DecisionTrailPanel";
import { AssetTag, ErrorBox, type OpenTrail } from "./pieces";
import { useRead } from "./useRead";

export function TradePage({ simId, trade }: { simId: number; trade: number }) {
  const read = useCallback(() => fetchTrade(simId, trade), [simId, trade]);
  const { data: page, error } = useRead(read);
  const [trail, setTrail] = useState<string | null>(null);
  const closeTrail = useCallback(() => setTrail(null), []);

  return (
    <section>
      <a href={`#/sims/${simId}`} className="mb-4 inline-block font-mono text-[13.5px] tracking-wider text-dim hover:text-amber">
        &lt; The sim
      </a>
      {error && <ErrorBox title="Cannot read this trade" text={error} />}
      {!page && !error && <p className="text-center font-mono text-dim">Loading...</p>}
      {page && <TradeBody page={page} onOpenTrail={setTrail} />}
      {trail !== null && <DecisionTrailPanel key={trail} simId={simId} decision={trail} onClose={closeTrail} />}
    </section>
  );
}

function TradeBody({ page, onOpenTrail }: { page: TradePageAnswer; onOpenTrail: OpenTrail }) {
  const t = page.trade;
  const openedBy = t.decision;
  return (
    <>
      <h1 className="mb-3 text-center text-[2.1rem] leading-tight tracking-[.02em]">
        Trade {t.position}: <AssetTag asset={t.asset} /> {t.direction}
      </h1>
      <p className="mb-6 text-center font-mono text-dim">The Trade page is being built.</p>
      {openedBy && (
        <button
          type="button"
          onClick={() => onOpenTrail(openedBy)}
          className="border-[1.5px] border-rule px-[1.5ch] py-1 font-mono text-[13.5px] tracking-wider hover:text-pale"
        >
          How it was opened
        </button>
      )}
      <ul className="mt-4 font-mono text-[14px]">
        {page.position_steps.map(({ step, kind, decision }) => (
          <li key={step}>
            {decision ? (
              <button type="button" onClick={() => onOpenTrail(decision)} className="hover:text-amber">
                Step {step}: {kind}
              </button>
            ) : (
              `Step ${step}: ${kind}`
            )}
          </li>
        ))}
      </ul>
    </>
  );
}
