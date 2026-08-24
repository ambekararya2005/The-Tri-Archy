MANTIS
Mandate & Agent Threat Intelligence System
Every fraud model in production was trained on payments a human started. The agentic rails went live last year with no fraud history, no labels, and no published detection signatures. You can't train a defender on data that doesn't exist — so you manufacture it. That is the whole reason identify → generate → defend has to be one loop, and it's the argument the other teams won't be making.



MANTIS: a red-team/blue-team lab for agent-initiated payments. Pillar one is a machine-readable atlas of 42 GenAI fraud vectors that drives the code rather than sitting in a slide. Pillar two is a three-layer attack foundry that synthesises a calibrated population of legitimate payments and then injects those vectors into it — with a published fidelity scorecard, not a fidelity claim. Pillar three is a five-layer defence that scores each authorisation in under 50 ms, reports recall at a fixed 0.1% false-positive rate the way a real issuer does, and proves it catches three attack families it was never trained on. Then you close the loop: an evolutionary adversary reads the detector's own explanations, mutates to evade, the detector retrains, and you show the evasion curve collapsing across rounds. That last chart is your submission's whole argument in one image.




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

## What runs today (Day 3)

No network, no GPU, no API key, no Kaggle token. `make demo` is the acceptance test.

```
make install     # editable install plus dev tools
make demo        # schema -> atlas -> corpus -> population -> dataset -> tests
```

Individual stages, each runnable on its own:

| Command | What it prints |
|---|---|
| `make schema` | the frozen `TxEvent` contract, v1.1.0 |
| `make atlas` | 42 vectors, and the **honest count** of how many have a working injector |
| `make corpus` | the committed LLM content corpus, and one specimen of each kind |
| `make population` | 200k calibrated legitimate authorisations + the calibration figure |
| `make dataset` | the labelled dataset, class balance, per-attack counts, the separability table, and a full sample of what an agent read before it paid |
| `make probe` | best-single-feature AUC per injector, against a small background |
| `make test` | the suite |

**Where it stands.** 42 vectors mapped, **15 with a working injector** — the atlas
is a dependency of the generator, not documentation next to it, and
`import mantis.foundry.injectors` fails if that ever stops being true. Seven of
the fifteen are agentic mandate attacks, deliberately split so that two of them
(F1-01 cart-mandate tampering, F1-03 refund-logic hijack) satisfy **every**
protocol rule and can only be caught behaviourally or from the text the agent
read. No attack in the dataset is separable by any single column.

Still to come: the fidelity scorecard, the five-layer Mandate Firewall, the
evolutionary adversary loop, and the live defence console.
