# Config Feature Plan

## Goal
Allow admins to view and edit scoring configuration through the admin panel UI.
The agent reads config from the DB at runtime instead of hardcoded values.
Falls back to hardcoded defaults if DB is unavailable.

---

## DB Table: `config`

```sql
create table config (
  key         text primary key,
  value       jsonb not null,
  label       text,
  description text,
  updated_at  timestamptz default now()
);
```

### Default Rows

| key | value | label | description |
|-----|-------|-------|-------------|
| `dimension_weights` | `{"delivery_ownership": 0.18, "leadership_signals": 0.15, "business_impact": 0.15, "stakeholder_management": 0.12, "evidence_credibility": 0.12, "pm_readiness": 0.10, "strategic_thinking": 0.08, "communication_clarity": 0.05, "technical_fluency": 0.03, "authenticity_confidence": 0.02}` | Dimension Weights | Interview scoring weights per PM dimension (must sum to 1.0) |
| `blend_llm_weight` | `0.75` | LLM Interview Weight | Weight of LLM behavioral score in final blend |
| `blend_formula_weight` | `0.25` | Formula CV Weight | Weight of formula CV baseline in final blend |
| `not_serious_llm_penalty` | `35.0` | Not-Serious LLM Penalty | Points deducted from llm_weighted when not_serious flag raised |
| `not_serious_score_cap` | `30.0` | Not-Serious Score Cap | Maximum overall score when not_serious flag raised |
| `recommend_threshold` | `75.0` | Recommend Threshold | Minimum overall score to receive Recommend |
| `reservations_threshold` | `55.0` | Minimum score for Recommend with Reservations |

---

## agent.py Changes

### Config cache
```python
_config_cache: dict = {}
_config_loaded: bool = False

def _load_config() -> dict:
    """Load config from DB once, cache it. Falls back to hardcoded defaults."""
    global _config_cache, _config_loaded
    if _config_loaded:
        return _config_cache
    
    DEFAULTS = {
        "dimension_weights": {
            "delivery_ownership": 0.18, "leadership_signals": 0.15,
            "business_impact": 0.15, "stakeholder_management": 0.12,
            "evidence_credibility": 0.12, "pm_readiness": 0.10,
            "strategic_thinking": 0.08, "communication_clarity": 0.05,
            "technical_fluency": 0.03, "authenticity_confidence": 0.02,
        },
        "blend_llm_weight": 0.75,
        "blend_formula_weight": 0.25,
        "not_serious_llm_penalty": 35.0,
        "not_serious_score_cap": 30.0,
        "recommend_threshold": 75.0,
        "reservations_threshold": 55.0,
    }
    
    sb = _get_supabase()
    if sb is None:
        _config_cache = DEFAULTS
        _config_loaded = True
        return _config_cache
    
    try:
        rows = sb.table("config").select("key, value").execute().data or []
        cfg = dict(DEFAULTS)  # start from defaults
        for row in rows:
            cfg[row["key"]] = row["value"]
        _config_cache = cfg
    except Exception:
        _config_cache = DEFAULTS
    
    _config_loaded = True
    return _config_cache

def invalidate_config_cache():
    """Call this after admin saves config so next request re-reads from DB."""
    global _config_loaded
    _config_loaded = False
```

### Usage in finalize_node
Replace hardcoded values with calls to `_load_config()`:

```python
cfg = _load_config()
weights        = cfg["dimension_weights"]
llm_blend      = float(cfg["blend_llm_weight"])
formula_blend  = float(cfg["blend_formula_weight"])
penalty        = float(cfg["not_serious_llm_penalty"])
score_cap      = float(cfg["not_serious_score_cap"])
rec_threshold  = float(cfg["recommend_threshold"])
res_threshold  = float(cfg["reservations_threshold"])
```

### Usage in _weighted_score
Pass weights as parameter instead of global WEIGHTS dict.

---

## api/main.py Changes

### GET /admin/config
Returns all config rows as a list.

### PUT /admin/config/{key}
Updates a single config key value in the DB.
Calls `agent.invalidate_config_cache()` after successful update.

---

## Frontend Changes

### Router
Add a `configView` boolean state to AdminPage.
Header gets a settings icon button that toggles between candidates list and config page.

### ConfigPage component (inline in AdminPage)
Sections:
1. **Dimension Weights** — 10 number inputs (0.00–1.00), shows running sum, warns if ≠ 1.0
2. **Blend Weights** — 2 number inputs (LLM weight + formula weight), must sum to 1.0
3. **Thresholds** — Recommend threshold, Reservations threshold (0–100)
4. **Not-Serious Penalty** — LLM penalty points, score cap

Each section has a **Save** button that calls `PUT /admin/config/{key}`.
Shows success/error feedback.
Default values are pre-filled from `GET /admin/config`.

---

## Implementation Order
1. ✅ Create `config` table in Supabase (user runs SQL)
2. Seed default rows via Supabase client
3. Add `_load_config()` + `invalidate_config_cache()` to agent.py
4. Update `finalize_node` to use config values
5. Add `_weighted_score` to accept weights param
6. Add API endpoints in main.py
7. Build ConfigPage in frontend
8. Add settings toggle to admin header
