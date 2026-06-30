# Coruscant — Global Exposure Intelligence

**Architecture & sequencing plan of record.** 2026-06-30.
Supersedes the ad-hoc pillar notes. Grounded in the real graph, stress-tested by an adversarial review.

---

## 0. The product (the north star everything serves)

Coruscant answers **one question for a portfolio holder** (family office, fund manager, allocator):

> *A random event happens somewhere in the world. **Does it touch my portfolio — and how?***

The user forwards their portfolio (PDF / holdings list — ingestion mechanism TBD). We resolve each holding to an entity in the graph and **monitor it continuously**. When something happens — a strike at a Chilean lithium mine, a missile on an AWS datacenter in the UAE — we trace the blast radius through ownership, supply chains, and geography to the holdings it actually touches, and surface it as an **insight with its chain of evidence**.

We do **not** give stock recommendations. We give **orientation**: *what changed, who it hits, why we believe it, what to investigate.* The PM can't watch all the news; we watch the network for them.

**Everything else in this document — the company graph, beneficial ownership, PEP/sanctions, supply chains, events — is *substrate* for that one query.** The pillars are not the product; the **event → who → your portfolio** path is.

```
EVENT ──hits──▶ FACILITY / PLACE / SECTOR
                     │ operated by / located in
                     ▼
                 COMPANY ──supplies*──▶ COMPANY ──owned by──▶ YOUR HOLDING
                     └──────────── chain of evidence at every hop ───────────┘
```

---

## 1. Honest starting state (the real graph, not the brochure)

A reviewer from Sayari/Moody's will open the graph in the first five minutes. So will we.

**Nodes (1,054 total):** 53 `Company`, 661 `Person`, 152 `Subsidiary`, 58 `Filing` (+ sector/country).
**Edges:** `insider_holding` **494** (Form 4 — our *largest* people-edge class), `references` (co-mention, ~190, incl. 85 verified cross-border US/UK/India), `has_subsidiary` 152, `board_member` 117, `employs` 216, `in_sector` 53, board interlocks 4.

Three corrections to how we've described this:

1. **`has_subsidiary` (Exhibit 21) is NOT an ownership edge.** It's a *list of subsidiary names* with a jurisdiction string — no percentage, no holder, no control direction, and the target is a bare unresolved `Subsidiary` node, not a resolved company. It asserts "is a significant subsidiary," nothing more.
2. **There is no portfolio / holding / fund concept in the graph at all.** The product's front door does not exist yet. *But* `insider_holding` (Form 4) is a real `person → holds shares of → company` primitive, and **13F / 13D-G filings (free, EDGAR) are the obvious first portfolio-holder source** — we are closer than zero.
3. **The store is a JSON blob over SQLite** (`InMemoryKnowledgeGraphStore`), despite ADR-0001 saying "why Neo4j." It is a prototype. **You cannot run multi-hop `supplies*` exposure traversals over it at GLEIF/OpenSanctions scale.** A real graph store is a prerequisite, not a footnote.

What *is* real and load-bearing: **provenance-first** (every edge carries its source statement) and a **spatial Atlas UX** (the 3D force graph is the primary surface, not a tab). Those are the moat.

---

## 2. Invariants (the rules every later decision obeys)

1. **No edge without evidence.** Every relationship and attribute carries the source statement that produced it. Already our discipline; the open substrate (FollowTheMoney / OpenSanctions / GLEIF / BODS) is *natively* statement-based, so we adopt a model that is the reference implementation of the one we chose — a strategic gift.
2. **Internal surrogate ID is the primary key; LEI / CIK / DIN / registry-number are external *anchors*.** LEI covers ~2.5M financial-market entities — <1% of companies. It is a join enrichment, never the primary key for the private long tail where UBO intelligence matters.
3. **Native-script canonical; romanization for recall only.** A transliteration is an alias and a blocking key — *never* the sole basis for a merge.
4. **Declared ownership ≠ beneficial ownership ≠ accounting consolidation.** Three distinct edge types (`owns%` / `beneficial_owner_of` / `consolidates`). Never silently equated. GLEIF L2 is consolidation, not %-ownership.
5. **Absence is signal; suppression is not deletion.** A missing parent is `parent_unknown {reason}` (e.g. "legally barred"); a record a hostile registry stopped publishing (Russia's Dec-2024 amnesia for sanctioned entities) becomes an `ended` edge with reason, never a delete. **Exception, see §7: GDPR erasure for EU natural persons overrides "never delete" — those need tombstoning + a retention-basis answer.**
6. **Bitemporal.** Every fact carries *valid-time* (true in the world from–to) and *system-time* (when we believed it). "Was this counterparty sanctioned *on the date my customer transacted*?" is a core query and unanswerable without it.
7. **`access_tier` rides every UBO edge** (`public` / `legitimate-interest` / `restricted-authority` / `aggregator-licensed`), and a **query-time policy engine enforces it.** A tag nobody enforces is worse than no tag — it's a compliance violation with a paper trail.

---

## 3. The substrate pillars (and the portfolio layer they feed)

| # | Pillar | Question | Primary source | Access reality |
|---|---|---|---|---|
| **0** | **Portfolio layer** *(the front door)* | "What do I hold?" | **EDGAR 13F / 13D-G** (free) → then user-forwarded portfolios | Free; parsing + entity-resolution work |
| **1** | **Identity / keys** | "Does this entity exist; what's its canonical id?" | Internal surrogate + **GLEIF LEI** anchor + national registries | LEI CC0/free but sparse |
| **2** | **Ultimate beneficial ownership** | "Who actually controls it, and how much?" | **UK PSC** (free, statutory) + national BO registers + OpenSanctions FtM aggregator | Fragmented; EU gated; US CTA non-public |
| **3** | **PEP / sanctions** | "Is this person/entity politically exposed or listed?" | **OpenSanctions** (PEP ~949K, sanctions ~100K) | CC-BY-NC → **paid Reseller/OEM; dev-time use needs written clarification** |
| **4** | **Event → exposure** | "What happened; does my portfolio touch it?" | **GDELT** (events) → facility geodata → supply-chain edges | Free = *proximity*; paid (SPLC/FactSet) = *magnitude* |

**The pillars are a dependency chain, not a menu:** Pillar 4 (the product) cannot reach a portfolio without ownership (Pillar 2) and cannot fire the event→entity join without entity resolution (§4). **Entity resolution is the load-bearing wall under all of it.**

---

## 4. Entity resolution — the wall everything rests on

> *There is no global primary key.* The same entity is `ПАО Сбербанк` / `Sberbank of Russia PJSC`; `ACME HOLDINGS LLC (Delaware)` / `Acme Holdings, L.L.C.` / `ACME HLDGS`. Get it wrong two ways, both expensive:
> - **False negative** → a UBO/sanctions chain silently breaks and exposure *hides* (the dangerous one for us).
> - **False positive / over-merge** → we fabricate a link no source asserted — a direct violation of Invariant #1.

**Spine:** `nomenklatura` / `yente` (OpenSanctions' MIT-licensed ER stack). It is native to FollowTheMoney (zero impedance with our ingest), the scorer is **deterministic and auditable** (matches our provenance requirement), and its **Resolver is a reversible, versioned graph of `same`/`different`/`undecided` judgements** — a merge we can audit and undo. We reject Senzing (closed-box scorer, per-record pricing) as the spine; keep it as a commercial fallback only.

**Pipeline:** normalize/transliterate (AnyAscii + libpostal; native script stays canonical) → block (over-generate candidates) → score (`logic-v2` default; self-hosted open-weight LLM for hard cross-script pairs — self-hosted for auditability + no PII egress) → **cluster.**

**Four corrections the review forces — these are the parts that actually bite:**

1. **Clustering must be merge-resistant, NOT connected-components.** `A~B` and `B~C` at 0.9 each does *not* mean `A~C`; connected-components will fuse three entities and, at scale, silently merge two unrelated multinationals on one bad bridge edge. Use correlation/weighted clustering with persisted `different` judgements that break bridges. *This is the #1 ER risk, above pairwise accuracy.*
2. **Benchmark F1 ≠ production accuracy.** The ~98% numbers are on curated sanctions/PEP pairs rich in attributes. Our hardest target is the **152 bare subsidiary strings** (a name + a US state, no key) — a thin-record blocking-and-scoring problem the benchmarks don't measure. Plan for far lower real-world precision there.
3. **Person ER is harder and higher-stakes than company ER.** Name-only matching against 949K PEPs floods false positives ("Maria Silva," "Wang Wei"), and **a false-positive PEP hit on a customer's counterparty is a defamation/discrimination exposure, not a data blip.** Requires a precision gate + a human-review SLA with a bounded backlog — not "human-in-the-loop" hand-waving.
4. **Stable canonical IDs across re-resolution.** Registries update daily; re-clustering must not change the `canonical_id` a customer bookmarked yesterday. National keys (DIN, officer_id) collapse the *intra-*jurisdiction problem only — the cross-jurisdiction person link is still the hard part.

---

## 5. Sequencing — free-first, product-led, honestly sized

Each phase ships something demoable. Free before paid at every tier. *(Durations are honest, not aspirational.)*

**Phase 0 — Substrate & keys *(a quarter, not "weeks"; free)*.** Stand up a **real graph store** (the JSON/SQLite prototype cannot do §4's traversals at scale) + the **nomenklatura/yente ER service** + internal surrogate keys; ingest **GLEIF Golden Copy** as an anchor; **resolve the 152 subsidiary strings** (the hardest ER targets, 14% of nodes); and — in writing, *now*, not "in parallel" — **clarify OpenSanctions dev-time-use + OpenCorporates post-D&B-acquisition terms.** This is the load-bearing quarter; under-sizing it cascades.

**Phase 1 — PEP/sanctions on the people we already have *(fastest wow)*.** Screen the **661 Person nodes** against OpenSanctions PEP + sanctions on **on-prem yente** (bulk, not the metered API). *Caveat the review surfaced:* nearly half those people are **insider-holders (Form 4)**, not officers — a different PEP base rate. Internal-only until the Reseller/OEM license closes (so it gates *external* demo, not building).

**Phase 2 — The portfolio front door *(makes the product real)*.** Parse **EDGAR 13F / 13D-G** (free) into `Fund → holds → Company` edges — the holding primitive the graph lacks — then accept **user-forwarded portfolios**, resolving holdings to entities. *Now the product has an input.*

**Phase 3 — Real ownership edges *(the missing substrate)*.** **UK PSC** first (free, statutory, real %-bands + officer interlocks), then Brazil CNPJ/QSA, France RNE, Canada ISC, India MCA/DIN; BODS frozen snapshot (date-stamped stale) as seed. This is the ownership class the graph has never had — and the precondition for closing the exposure loop to a holding.

**Phase 4 — Event → exposure.** **GDELT** events (free; a *signal*, never an ER input — its org-extraction is too noisy) → **facility geodata** (GEM/ICMM/datacenter sets) → **supply-chain edges**. *Honest naming:* the free tier (OEC bill-of-lading) gives **event–network *proximity***, not exposure *magnitude*. Calling it "exposure" before we buy directional, $-weighted chains (Sayari / Bloomberg SPLC / FactSet) is the over-claim the review flagged. Buy magnitude data only after the proximity thesis is proven.

> **Critical path:** real store + ER spine + surrogate keys → screen the 661 people → portfolio edges (13F) → ownership edges (UK PSC) → event-proximity (GDELT) → *then* paid magnitude. Free at every tier first; pay only to ship commercially and at scale.

---

## 6. Cost & access — the load-bearing risk list

**Free & commercially clean:** GLEIF (CC0), UK Companies House, Brazil CNPJ, France RNE, GDELT data (pay Google for BigQuery *compute*), EDGAR 13F/13D-G. **Attribution-encumbered:** GEM/ICMM (CC-BY — needs **per-node license lineage** so the UX renders correct attribution). **Paid / our spend line:** OpenSanctions (Reseller/OEM), OpenCorporates Enterprise, Sayari/SPLC/FactSet (5–6 figure). **And the column the draft omitted:** **infrastructure** — a real graph DB over millions of nodes + daily GDELT + bulk registries is *not free even when the data is.*

The honest landmines:

- **EU UBO public access collapsed** (CJEU C-37/20, Nov 2022); AMLR restores only *legitimate-interest* access (not us as general public) through 2027. Free EU UBO bulk is gone.
- **US CTA register is non-public** (FinCEN, gutted Mar 2025). No clean US federal UBO feed.
- **Russia "registry amnesia"** — sanctioned entities' EGRUL records restricted since Dec 2024 (*exactly* the high-risk entities). Never depend on the live FNS feed; use OpenSanctions' archived mirror; model vanished records as `ended`.
- **OpenCorporates is now inside Dun & Bradstreet** — an incumbent. Not an independent open pillar; do not make it load-bearing.
- **OpenSanctions CC-BY-NC may bar commercial *development*, not just shipping** — get it in writing before Phase 1.
- **Sanctions screening is a *regulated, liability-bearing* capability.** Surface a hit a customer relies on and you inherit screening-vendor liability (a missed hit can mean facilitating a sanctioned transaction). Needs a false-negative-recall posture + reliance disclaimers.
- **GDPR.** A database of named persons, family links, partial DOBs, political exposure across EU subjects needs a lawful basis + a DPIA, and **erasure rights collide head-on with "never delete"** — resolve with tombstoning + retention basis, not celebration of immutability.
- **Contradictory sources need a survivorship policy** (GLEIF says DE, OC says NL) — store both (statement-based), but the graph the user *sees* needs a source-precedence rule. Incumbents have teams on this.

---

## 7. The differentiator (why we win without out-covering anyone)

Coverage is unwinnable — everyone converges on ~500M companies. We don't play that game. Three gaps incumbents *can't or won't* close:

1. **Ownership *evidence* is shallow everywhere.** Sayari/Moody's/D&B show a parent→sub edge, **not the document and clause it came from.** Because our entire ingest is statement-based, **"show me why you believe this edge" is a one-click action for *every* edge** — not a curated few. Out-*experience* Sayari (the closest to our thesis); don't out-data it.
2. **Spatial orientation is absent everywhere** — visualization is a bolted-on "Visualize" tab. Our Atlas *is* the interface. The pitch is **"you understand the network in ten seconds,"** not "we have the data."
3. **The 2025–26 access shock makes auditable provenance a compliance asset.** As US (CTA) and EU (6AMLD) lock UBO down, a black-box "trust us, the parent is X" becomes a liability; our reproducible, source-cited edge becomes a feature.

**Beachhead:** family offices + smaller funds + investigative/NGO users priced out of opaque enterprise quotes — win **orientation + provenance + portfolio-exposure** there, move up-market. **Moat:** time-to-understanding × auditability, anchored on a use case (does this event touch *my* book?) the incumbents treat as a data problem, not an orientation problem.

---

## Appendix — what we explicitly cannot do yet (say it out loud)

No portfolio data in the graph (Phase 2 fixes it). No real ownership edges (Phase 3). Exposure *magnitude* needs paid data (Phase 4 tier-2). EU UBO largely gated; US CTA closed. Sanctions-screening liability + GDPR unresolved. The current store won't scale. **This plan is how we earn each of those, in order, free-first — with entity resolution as the wall and one-click provenance as the product.**
