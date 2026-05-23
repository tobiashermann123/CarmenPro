# CarmenPro — Engineering Plan

## Phase 1: Data & Foresight Foundation (Weeks 1–3)
**Goal:** Running data pipelines before any model or execution code is written.

### 1A — Supabase Schema (Week 1)
Files: `infrastructure/supabase/migrations/`

Tables to create (exact schema in Phase 1 brief):
- `raw_fundamentals` — OpenBB balance sheet / cash flow snapshots
- `price_timeseries` — daily OHLCV per ticker
- `foresight_scores` — LLM output scores per ticker per report date
- `portfolio_ledger` — internal position and trade log (reconciled against IBKR)
- `documents` — metadata for ingested PDFs / SEC filings
- `document_chunks` — pgvector embeddings (1536-dim)

### 1B — Layer 1: Foresight Pipeline (Week 2)
Files: `layers/layer1_foresight/`

Steps:
1. PDF/SEC filing ingestion via `unstructured` → clean text + tables
2. Chunking + embedding via `llama_index` → stored in pgvector
3. Local LLM inference via `vllm` (Llama-3-8B) → bottleneck keyword extraction
4. Output: `foresight_scores` row per ticker per document with numeric sentiment score (-1.0 to +1.0) and flagged themes (e.g., "liquid_cooling", "photonics", "grid_capacity")

### 1C — Layer 2: Fundamental Data Pipeline (Week 3)
Files: `layers/layer2_data/`, Prefect flows

Steps:
1. OpenBB pulls: balance sheet, cash flow statement, income statement, enterprise value multiples
2. Prefect flow: nightly schedule, rate-limit handling, retry logic, failure alert
3. Writes to `raw_fundamentals` and `price_timeseries`
4. Data quality gate: reject and alert if >10% of fields are null

---

## Phase 2: Modeling & Target Generation (Weeks 4–5)
**Goal:** Intrinsic value per share + strike price targets with margin of safety logic.

### 2A — DCF Engine (Week 4)
Files: `layers/layer4_valuation/dcf.py`

Inputs: FCF from `raw_fundamentals`, WACC assumptions, growth rates
Output: Intrinsic value per share, current margin of safety %

Constraints:
- Base MoS threshold: 30%
- If foresight_score for ticker's sub-sector > 0.6 (strong bottleneck signal): lower MoS to 15%
- If FCF Yield < 7% or Piotroski F-Score < 7: exclude from consideration regardless

### 2B — Qlib Integration (Week 4–5)
Files: `layers/layer4_valuation/qlib_runner.py`

Steps:
1. Feed Supabase fundamentals + foresight scores into Qlib dataset
2. Backtest FCF Yield + Piotroski constraints across 2015–2024
3. Output: ranked list of tickers with target put strike prices
4. Tail risk allocation: reserve 1–2% of projected yield for SOXX OTM puts (hardcoded in allocation logic)

---

## Phase 3: Execution & Audit Loop (Weeks 6–8)
**Goal:** Live orders to IBKR, daily reconciliation, automatic halt on mismatch.

### 3A — IBKR Gateway Docker (Week 6)
Files: `infrastructure/docker/`

- IB Gateway in isolated Docker container
- Environment variables for credentials (never in image)
- Health check endpoint

### 3B — Execution Engine (Week 6–7)
Files: `layers/layer5_execution/executor.py`

Hard rules (enforce in code, not config):
- Order type: LIMIT only — raise exception if Market Order attempted
- Mid-point pricing: `(bid + ask) / 2` — never cross the spread
- Liquidity filter: if `open_interest < 100`, log and skip — do not place order
- FX logging: record USD/EUR rate at time of each order in `portfolio_ledger`

### 3C — Reconciliation Engine (Week 7–8)
Files: `layers/layer5_execution/reconciler.py`

Steps:
1. Download daily IBKR Flex Query CSV (reuse CarmenBot's Flex parser pattern)
2. Compare IBKR positions + cash to `portfolio_ledger` in Supabase
3. If any discrepancy > €0.01: set `execution_halted = True` in a `system_state` table, send alert
4. Execution engine checks `execution_halted` flag before every order — refuses to place if True
5. Manual override required to resume — never auto-reset

---

## Risk Engineering Checklist (must be verifiable in code review)
- [ ] No Market Orders anywhere in execution layer
- [ ] Open Interest < 100 check in executor.py
- [ ] MoS override logic tested with unit test (foresight score 0.7 → 15% MoS)
- [ ] Reconciliation halt tested with injected mismatch
- [ ] Tail risk SOXX put allocation present in Qlib allocation layer
- [ ] FX exposure logged on every trade
- [ ] All secrets in .env, not in code
- [ ] Prefect flows have failure alerting configured
- [ ] pgvector extension enabled in Supabase migration
