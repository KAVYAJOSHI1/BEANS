# BEANS: Improvement Execution Plan (reviewed and implemented)

This replaces the first draft of the plan. It records what was built, what was changed from the draft and why, and what
is left. The sidebar work is in [`BEANS_SIDEBAR_UI_REFACTOR_PLAN.md`](BEANS_SIDEBAR_UI_REFACTOR_PLAN.md).

## Corrections to the draft's baseline

| Draft said | Actual (code) |
|---|---|
| Review Queue holds wallets with P in [0.20, 0.40] | It holds open alerts that are uncertain (P within 0.5 ± 0.15, or confidence < 0.5) **and** near-misses from P = 0.20 up to the alert threshold (`beans/api/routes/review.py`) |
| Verdicts are `CONFIRM_ILLICIT` / `FALSE_POSITIVE` | `TRUE_POSITIVE` / `FALSE_POSITIVE`; retraining weight 5× is correct |
| Live Monitor "switches" between simulated and P2P feeds | It reads `collector.status` and `watch.status` from the inbox folder and the database; throughput figures are one run's snapshot |

## Status

| Item | Status | Where |
|---|---|---|
| Section 63 BSA 2023 certificate (alert and case) | **Done** | `beans/report/bsa63.py`, `beans/api/routes/evidence.py`; filed as a legal request, four-eyes approval; `tests/test_bsa63.py` |
| Cash-Out Forecast page | **Done** | `ui/src/components/ForecastPage.jsx` on `GET /api/forecast` (E7) |
| Mixer Lab page | **Done** | `ui/src/components/MixerLab.jsx` on `GET /api/mixer/transactions`, `/api/mixer/{txid}` (E6) |
| Mempool latency: unconfirmed-first monitoring | **Done** (replaces "mempool pre-crime") | `watch.quick_check`, `IngestWorker.quick_watch`; `tests/test_unconfirmed.py` |
| THORChain-style swap memo capture | **Done** | `beans/enrich/swaps.py`, collector `OP_RETURN` parsing, `CROSS_CHAIN_EXIT` rule; `tests/test_swaps.py` |
| Sidebar: groups, collapse, icon rail | **Done** | `ui/src/components/Sidebar.jsx` |
| Threat Matrix (Lazarus / APT38 profiling) | **Dropped** | no attribution data behind it; naming real threat groups would be an unsupported claim |

## What changed from the draft, and why

- **Section 63 certificate.** Kept, with limits: BEANS drafts, people sign. Part A (person in charge) and Part B (expert) stay
  blank; BEANS never asserts lawful control, regular use or who the certifier is. A "QR admissibility seal" became a
  *verification code*, because a code proves integrity, not admissibility. The Merkle tree became a hashed record list plus
  one digest over the sorted record hashes (the sealed annex already covers integrity). The certificate goes through the
  existing four-eyes approval and audit trail. Counsel should check the wording against the Schedule to Section 63.
- **Mixer "demixing" is not possible, so it was not built.** E6 already does the amount matching (certain change links, 1/k on
  equal outputs). Equal outputs are unlinkable from amounts; Whirlpool and Wasabi 2.0 cannot be unmixed that way. Mixer Lab shows
  the anonymity set and the links honestly. WabiSabi subset-sum is a possible later addition, capped because it explodes
  combinatorially.
- **Instant-swap detection.** FixedFloat / ChangeNOW / SideShift cannot be fingerprinted from Bitcoin data and the XMR / Tron
  side is invisible; they need `known-entities`. What *is* on the chain is a THORChain-style `OP_RETURN` memo naming the
  destination, so that is what was built.
- **"Mempool pre-crime".** The collector already worked from the mempool relay, so a new sniffer was not the gap. The gap was
  latency (scoring at most once a minute, watchlist checked only after scoring). The fast path now checks new files against
  the watchlist and seed wallets at load time and reports `UNCONFIRMED_MOVEMENT`. It is a heads-up and never a freeze: an
  unconfirmed transaction can be replaced (RBF is flagged) or dropped and has reached no exchange. The tag `0-CONF_PRE_CRIME`
  was rejected as a name for a legal setting.
- **Sidebar.** Search was skipped (Ctrl+K already exists), role-based hiding already existed, and the structure is five groups:
  Monitor, Investigate, Intelligence, Legal & Evidence, Data.

## Left for later

- WabiSabi (variable-amount) subset-sum, capped.
- Pre-arming a legal draft before the deposit (the draft generator needs a real deposit to cite).
- Real-data validation of the E6, E7 and E8 numbers: everything measured so far is synthetic.
- Chainflip and other swap services that do not use a memo.
