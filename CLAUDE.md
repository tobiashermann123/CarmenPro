# CarmenPro — Lead Engineer Context

## What You Are Building
A fully automated, quantitative value-investing infrastructure for a private EUR-denominated fund (~€100,000). The system targets AI and hardware supply chain equities. It predicts structural bottlenecks via LLM analysis, identifies mispriced equities via DCF models, and generates yield by writing cash-secured put options through Interactive Brokers.

## Your Role
You are the Lead Engineer. The Program Manager (Claude in conversation) provides strategy, phased briefs, and architectural decisions. You implement, test, and verify. When a phase brief arrives, execute it completely before asking for the next one.

## Non-Negotiables
- **All software is open-source only** — no paid SaaS, no licensing overhead
- **IBKR execution**: Limit Orders only — Market Orders are forbidden in all execution code
- **Reconciliation gate**: If Supabase ledger ≠ IBKR Flex ledger to the cent, the execution engine halts automatically
- **Tail risk hedge**: 1–2% of annual yield allocated to deep OTM SOXX puts — this must be in the Qlib allocation layer, not optional
- **Options liquidity filter**: Abort any trade where Open Interest < 100 contracts

## Technology Stack (locked — do not substitute)
| Layer | Purpose | Library |
|---|---|---|
| 1 | Macro foresight / NLP | `unstructured`, `llama_index`, `vllm` |
| 2 | Fundamental data + orchestration | `openbb`, `prefect` |
| 3 | Storage + BI | Supabase (PostgreSQL + pgvector), Metabase |
| 4 | Quantitative valuation + backtesting | `qlib` (Microsoft) |
| 5 | IBKR execution + reconciliation | `ib_insync` |

## Project Structure
```
CarmenPro/
├── CLAUDE.md                  ← you are here
├── ENGINEERING_PLAN.md        ← full phased roadmap
├── infrastructure/
│   ├── docker/                ← Docker Compose for IBKR Gateway + Metabase
│   └── supabase/              ← SQL schema migrations
├── layers/
│   ├── layer1_foresight/      ← PDF/SEC ingestion → LLM → foresight scores
│   ├── layer2_data/           ← OpenBB pullers, Prefect flows
│   ├── layer3_storage/        ← Supabase client, schema helpers
│   ├── layer4_valuation/      ← DCF engine, Qlib integration, MoS logic
│   └── layer5_execution/      ← ib_insync orders, ledger reconciliation
├── scripts/                   ← one-off admin / backfill scripts
├── tests/                     ← unit + integration tests per layer
└── docs/                      ← architecture diagrams, runbooks
```

## Key Risk Constraints the Code Must Enforce
1. **FX risk**: All EUR/USD positions tracked; execution layer logs FX exposure on every trade
2. **Slippage**: ib_insync scripts always use mid-point of bid-ask; never cross the spread
3. **Gap-down / black swan**: Deep OTM SOXX puts allocated systematically via Qlib — not manual
4. **Data quality**: If OpenBB returns stale or incomplete data, the valuation engine must refuse to produce a target — fail loudly, not silently

## Environment
- Python 3.11+
- Supabase project (credentials in `.env`)
- IBKR TWS / IB Gateway running locally or in Docker
- vllm requires CUDA GPU or Apple Silicon MPS for local inference
- All secrets in `.env` — never hardcoded

## Working Conventions
- Each layer is independently runnable and testable
- Layer interfaces are defined in `layers/__init__.py` — downstream layers import only from there
- Every Prefect flow has a name, description, and failure alerting configured
- Database migrations live in `infrastructure/supabase/migrations/` — numbered sequentially
