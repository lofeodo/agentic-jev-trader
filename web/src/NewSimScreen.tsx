// The New trading sim form (spec appendix 7, section 8): the three kinds of sim the app starts,
// the days, memory, model, what the sim would cost, and why it may not start. Its layout only,
// for now: nothing is asked of the API and nothing starts.
import { field, fieldLabel as label, formButton as button, SectionHeading } from "./pieces";

// The kinds the app starts, each with what it is for. Practice and tuning sims are command-line
// tools and never appear here.
const FORM_KINDS = [
  {
    kind: "measurement",
    title: "Measurement",
    says:
      "The exam: 30 days of one test period the agent was never adjusted on, played with memory " +
      "and without, side by side. Only these results count.",
  },
  {
    kind: "build-up",
    title: "Build-up",
    says:
      "One year without memory, whose stored trades become the memory later sims start from. " +
      "Done once; never counts.",
  },
  {
    kind: "free",
    title: "Free sim",
    says: "Any days you choose, outside the test periods. Never counts.",
  },
];

const MODELS = [
  { model: "claude-haiku-5-5", title: "Claude Haiku" },
  { model: "glm-5.3-flash", title: "GLM Flash" },
];

export function NewSimScreen() {
  return (
    <section>
      <h1 className="mb-1 text-center text-[2.1rem] leading-tight tracking-[.02em]">New trading sim</h1>
      <p className="mb-8 text-center text-[1.1rem] text-dim">
        Pick what to run; the form shows what it would cost before you start it
      </p>
      <p className="mb-6 font-mono text-[13.5px] tracking-wider text-dim">
        Not working yet: the form's layout only. Sims start from the command line for now.
      </p>

      <form onSubmit={(e) => e.preventDefault()} className="grid gap-8">
        <div>
          <SectionHeading number={1} title="Kind" says="Practice and tuning sims are command-line tools" />
          <fieldset disabled className="grid gap-3 px-[2ch]">
            <legend className="sr-only">Kind of sim</legend>
            {FORM_KINDS.map((k) => (
              <label key={k.kind} className="flex items-start gap-3">
                <input type="radio" name="kind" value={k.kind} className="mt-1.5 size-4 accent-amber" />
                <span>
                  <span className="font-mono tracking-wider">{k.title}</span>
                  <span className="block text-[15px] text-dim">{k.says}</span>
                </span>
              </label>
            ))}
          </fieldset>
        </div>

        <div>
          <SectionHeading number={2} title="Days" says="A test period, or your own dates" />
          <fieldset disabled className="flex flex-wrap items-end gap-6 px-[2ch]">
            <legend className="sr-only">Days</legend>
            <label className="grid gap-1">
              <span className={label}>Test period</span>
              <select className={field}>
                <option>Falling market</option>
                <option>Rising market</option>
              </select>
            </label>
            <label className="grid gap-1">
              <span className={label}>First day</span>
              <input type="date" className={field} />
            </label>
            <label className="grid gap-1">
              <span className={label}>Last day</span>
              <input type="date" className={field} />
            </label>
          </fieldset>
        </div>

        <div>
          <SectionHeading number={3} title="Memory" says="A free sim: with memory first" />
          <fieldset disabled className="grid gap-3 px-[2ch]">
            <legend className="sr-only">Memory</legend>
            <label className="flex items-center gap-3">
              <input type="radio" name="memory" value="memory_on" className="size-4 accent-amber" />
              <span className="font-mono tracking-wider">With memory</span>
            </label>
            <label className="flex items-center gap-3">
              <input type="radio" name="memory" value="memory_off" className="size-4 accent-amber" />
              <span className="font-mono tracking-wider">Without memory</span>
            </label>
            <label className="flex items-start gap-3">
              <input type="checkbox" className="mt-1.5 size-4 accent-amber" />
              <span>
                <span className="font-mono tracking-wider">Also play the same days the other way</span>
                <span className="block text-[15px] text-dim">Side by side, as a second sim.</span>
              </span>
            </label>
          </fieldset>
        </div>

        <div>
          <SectionHeading number={4} title="Model" says="The LLM that picks which past episodes Jev reads" />
          <fieldset disabled className="flex flex-wrap gap-6 px-[2ch]">
            <legend className="sr-only">Model</legend>
            {MODELS.map((m) => (
              <label key={m.model} className="flex items-center gap-3">
                <input type="checkbox" value={m.model} className="size-4 accent-amber" />
                <span className="font-mono tracking-wider">{m.title}</span>
              </label>
            ))}
          </fieldset>
        </div>

        <div>
          <SectionHeading number={5} title="Cost" says="Real dollars, asked again as choices change" />
          <dl className="flex flex-wrap gap-6 px-[2ch] font-mono">
            <div>
              <dt className={label}>Estimate</dt>
              <dd>--</dd>
            </div>
            <div>
              <dt className={label}>Spending cap</dt>
              <dd>--</dd>
            </div>
            <div>
              <dt className={label}>Left under the ceiling</dt>
              <dd>--</dd>
            </div>
          </dl>
        </div>

        <div className="grid gap-4">
          {/* The errors: empty unless something blocks the sim, then every refusal and its fix. */}
          <div aria-live="polite" aria-label="Why it cannot start" />
          <div>
            <button type="submit" className={button} disabled>
              Start the sim
            </button>
          </div>
        </div>
      </form>
    </section>
  );
}
