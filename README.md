MANTIS
Mandate & Agent Threat Intelligence System
Every fraud model in production was trained on payments a human started. The agentic rails went live last year with no fraud history, no labels, and no published detection signatures. You can't train a defender on data that doesn't exist — so you manufacture it. That is the whole reason identify → generate → defend has to be one loop, and it's the argument the other teams won't be making.



MANTIS: a red-team/blue-team lab for agent-initiated payments. Pillar one is a machine-readable atlas of 42 GenAI fraud vectors that drives the code rather than sitting in a slide. Pillar two is a three-layer attack foundry that synthesises a calibrated population of legitimate payments and then injects those vectors into it — with a published fidelity scorecard, not a fidelity claim. Pillar three is a five-layer defence that scores each authorisation in under 50 ms, reports recall at a fixed 0.1% false-positive rate the way a real issuer does, and measures honestly what happens to it on an attack family it was never trained on — which is a collapse, and the reason the loop below is load-bearing rather than decorative. Then you close the loop: an evolutionary adversary reads the detector's own explanations, mutates to evade, the detector retrains, and you show the evasion curve collapsing across rounds. That last chart is your submission's whole argument in one image.




The problem statement
Agentic commerce created a payment rail with a live fraud surface and zero labelled fraud data. MANTIS manufactures that data adversarially, then uses it to train the first defence that generalizes to attacks it has never seen.

Write it into the README and the .docx exactly like that. Then ground it in four numbers — every one of these is public and citable, which matters because judges discount unsourced framing:

Agentic traffic rose ~450% across 2025, concentrated on card payments and logins — a genuinely new third category of traffic alongside humans and classic bots (LexisNexis, 116 bn transactions).
Synthetic identity now sits in ~11% of frauds, up roughly eight-fold year on year — the fastest-growing type in the world.
India lost ₹22,495 crore to cyber fraud in 2025, with digital-payment fraud cases up ~27% YoY, and 92,000+ deepfake "digital arrest" incidents documented.
Unit 42 documented live prompt-injection attacks against shopping agents' cart mandates — and shipped no detection signatures with it. That gap is your product.
The framing that does the work
Do not present this as "we built a fraud classifier." Present it as: the rail Mastercard is building right now has no immune system, and here is how you grow one before the attackers arrive. Agent Pay, agentic tokens and "Know Your Agent" are Mastercard's own vocabulary — use it throughout. You are pitching to the people who own that roadmap.


---

## What runs today (Day 5)

No network, no GPU, no API key, no Kaggle token. `make demo` is the acceptance test.

```
make install     # editable install plus dev tools
make demo        # schema -> atlas -> corpus -> population -> dataset -> features -> l0 -> tests
```

Individual stages, each runnable on its own:

| Command | What it prints |
|---|---|
| `make schema` | the frozen `TxEvent` contract, v1.1.0 |
| `make atlas` | 42 vectors, the **honest count** of how many have a working injector, and any card the loop discovered |
| `make corpus` | the committed LLM content corpus, and one specimen of each kind |
| `make population` | 200k calibrated legitimate authorisations + the calibration figure |
| `make dataset` | the labelled dataset, class balance, per-attack counts, the separability table, and a full sample of what an agent read before it paid |
| `make probe` | best-single-feature AUC per injector, against a small background |
| `make derived` | the same gate run over the **built feature matrix**, because a single-column probe cannot see a feature that is two columns and a regression |
| `make features` | the 232-feature builder, with its three-tier leakage assertion fired deliberately |
| `make l0` | the nine deterministic clauses, per-clause precision and FP rate |
| `make firewall` | the five layers, the fusion weights, leave-one-family-out, and `RESULTS.md` (~15 min) |
| `make loop` | the evasion curve and the zero-day comparison → `data/generated/arena.json` (~30 min) |
| `make ood` | L3 against 18 hand-authored injections **and 10 benign controls in the same registers** — the number that says its 1.000 is about a corpus, not the open web |
| `make feed` | pre-scores 600 authorisations for the console, so the API fits nothing at request time (~2 min) |
| `make api` | the console backend on `:8000`, docs at `/docs` |
| `make web` | builds the React console (run `cd web && npm install` once first) |
| `make docx` | the submission document, **generated from RESULTS.md** — regenerate, never retype |
| `make test` | the suite |

## Seeing it run

```
make api                      # terminal 1 — the backend on :8000
cd web && npm install && npm run dev   # terminal 2 — the console on :5173
```

Press **Start authorisation stream**. Authorisations arrive one at a time and
are scored in front of you: a risk index, which layers fired, the decision, and
the three features that drove it. Rows resolve red or green as the outcome
lands.

Two things the console is careful about, because they are the difference between
a demo and a demonstration. The scored event and the ground truth are **separate
objects on the wire** — the UI renders the decision from one and reveals the
outcome from the other, so it cannot colour a row before the score arrives. And
the stream **says what it is**: the replay over-samples fraud roughly 25x against
its true 1% prevalence so that something happens while you watch, and that
sentence is printed in the console header rather than buried in a manifest.

The **Results** tab is static and reads every figure from `RESULTS.md` through
the API. Nothing on it is typed into the interface, so a retrain moves the
numbers on the screen without anyone editing TypeScript.

**Where it stands.** 42 vectors mapped, **15 with a working injector** — the atlas
is a dependency of the generator, not documentation next to it, and
`import mantis.foundry.injectors` fails if that ever stops being true. Seven of
the fifteen are agentic mandate attacks, deliberately split so that two of them
(F1-01 cart-mandate tampering, F1-03 refund-logic hijack) satisfy **every**
protocol rule and can only be caught behaviourally or from the text the agent
read. No attack in the dataset is separable by any single raw column.

Five defence layers exist: deterministic protocol rules (L0), a supervised GBDT
on 232 features (L1), an unsupervised residual monitor (L2), a page classifier
over the text the agent ingested (L3), and a streamed entity graph (L4). Every
number lives in `RESULTS.md`, which is written by the run rather than by hand.

**Two results we did not expect and are publishing anyway.** Unsupervised novelty
detection does not work on this data, and the reason is that *we made the attacks
distributionally faithful on purpose* — an attack built to sit on the legitimate
manifold is invisible to a method that measures distance from it, which is also
the property real agentic fraud has. And a supervised detector collapses on a
family it never trained on. What answers both is not a cleverer anomaly score: it
is protocol invariants that need no training data, plus a loop that manufactures
the attack before an attacker does.

**Say the zero-day result precisely.** The detector never trained on a single
real F1 event — that is the collapse, 0.811 down to 0.013. What recovers it to
0.539 is not the model generalising on its own: it is being handed *manufactured*
F1 data, produced by the loop from F1's atlas cards and injectors. The loop had
the generator; the detector never had the attack. **On a new rail you have a red
team, not a fraud history**, and the claim is that a red team is enough —
described-but-never-observed attacks can be manufactured, and training on the
manufactured version transfers to the real one.

Still to come: the fidelity scorecard.
