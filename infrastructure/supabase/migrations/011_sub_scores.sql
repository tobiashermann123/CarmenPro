-- Stores per-dimension sub-scores (e.g. Trend: 14/20, Momentum: 14/20).
-- Structure:
-- {
--   "technical":    {"trend": 14, "momentum": 14, "volume": 14, "pattern": 13, "rel_strength": 13},
--   "fundamental":  {"valuation": 16, "growth": 20, "profitability": 18, "health": 18, "moat": 15},
--   "sentiment":    {"news": 16, "social": 14, "analysts": 16, "institutional": 14, "insider_short": 12},
--   "risk":         {"volatility": 10, "downside": 10, "macro": 12, "liquidity": 12, "rr": 8},
--   "thesis":       {"catalyst": 17, "timing": 16, "asymmetry": 16, "edge": 16, "conviction": 16}
-- }
ALTER TABLE trade_signals
ADD COLUMN IF NOT EXISTS sub_scores_json JSONB;
