# BUILD SPEC — Gas Station Renovation Project Data System (Scoped Demo)

> Hand this file to Claude Code. It is the complete specification for the demo:
> what to build, how the pieces fit, the security guarantees that must hold, the
> Streamlit UI to add, how to run and deploy it, and the acceptance tests Claude
> Code should verify before considering the build done.

---

## 1. Purpose & context

A working proof of concept for a **single source of truth** across the gas
station renovation project lifecycle, **queryable in plain English**. It backs a
**Principal Business Analyst** interview: the deliverable is design judgment made
concrete, not a production deployment.

Two hard constraints from the owner, both already reflected in the code:

1. **Contracts are uploaded manually** — no DocuSign API. A signed PDF link is
   stored, with a record of who uploaded it.
2. **The AI is read-only** — it retrieves and presents data in response to
   natural-language questions; it can never INSERT / UPDATE / DELETE.

Scope of the demo: SQLite + synthetic data, modeled on a real APEC Imaging and
Canopies quote (Next Level Petroleum, 700 N Davis Dr, Warner Robins GA). It is
**not** wired to live Monday.com / email / CompanyCam — those are seed data here
and become integrations in the production tier (Section 9).

---

## 2. The domain model in one breath

A signed contract creates a project, which forks into two **parallel tracks**:

- **Permitting track** — mirrors Monday.com: a permit row (status) plus the
  permit person's free-text notes (`permit_updates`).
- **Materials track** — gathers quotes, which carry **design assets** (sign
  renders, canopy layouts) that flow across to the permit person to file. The
  design asset is the one object both tracks touch.

Materials split into **two scopes on different clocks**:

- `canopy_forecourt` — can be ordered as soon as it's approved.
- `signage` — **permit-gated**: cannot be ordered until the permit is approved.
- (`main_id` is broken out as its own scope because its permit implications
  differ — a reface of an existing cabinet is often exempt, a new sign isn't.)

Ordering flows to shipment and receipt, then **hands off to scheduling, which is
outside this system's boundary** (the owner's boss does scheduling).

---

## 3. Design principles (must be preserved)

- **Normalized.** Each fact stored once, related by foreign keys.
- **Documents are linked, not stored.** Every `*_path` / `*_url` column points to
  a file in storage; the DB holds only queryable facts about it.
- **Controlled vocabularies.** `material_scope`, `asset_type`, and status fields
  use fixed value sets so natural-language answers resolve reliably and terms
  can't silently diverge.
- **`project_scopes` makes "none yet" honest.** It declares which scopes a
  project actually expects and whether each is permit-gated, flagged manually at
  signing with `set_by` / `set_date` for accountability. We only report status on
  in-scope work, so a signage-only job never shows a misleading "canopy: none yet."
- **One quote PDF, many scope rows.** Real quotes bundle scopes into one
  document; store one `quotes` row per scope, all sharing a `quote_doc_path`.

---

## 4. File structure

```
gas-station-renovation-demo/
├── schema.sql          # data model (SQLite; inline >> PROD: notes for Azure SQL)
├── seed.py             # builds gas_renovation.db, loads synthetic data
├── query_engine.py     # read-only enforcement + approved query library + NL router
├── app.py              # CLI demo (kept; useful for quick checks)
├── streamlit_app.py    # NEW — web UI for the live demo (Section 7)
├── requirements.txt
├── README.md
└── BUILD_SPEC.md       # this file
```

The first four files already exist and pass their tests. Claude Code's job:
verify them, add `streamlit_app.py`, update `requirements.txt`, and confirm the
acceptance tests in Section 10.

---

## 5. Database schema

SQLite for the demo; production target Azure SQL Database. Tables:

- `projects` — site, customer, GC, status, start date.
- `contracts` — `signed_doc_path` (manual upload), `uploaded_by`, labor amount,
  status, signed date. A signed contract is what creates a project.
- `vendors` — APEC, Dualite, Federal Heath, Big Red Rooster; `material_category`.
- `quotes` — **one row per `material_scope`**, `amount`, `quote_doc_path`.
- `sales_orders` — `material_scope`, `status` ('approved' | 'ordered'), `quote_id`
  audit link back to the quote it came from.
- `shipments` — `expected_date`, `actual_date`, `received`. Last field tracked.
- `permits` — mirrors Monday status; `monday_item_url`, `jurisdiction`, `assigned_to`.
- `permit_updates` — one row per free-text comment. **PROD:** add
  `embedding VECTOR(1536)` for native vector search.
- `design_assets` — the bridge asset; `asset_type` (controlled), `asset_url`,
  nullable `vendor_id` / `quote_id` (art usually arrives with the quote, not always).
- `site_photos` — manual `companycam_url` links.
- `project_scopes` — `scope_type` (controlled), `in_scope`, `is_permit_gated`,
  `set_by`, `set_date`; UNIQUE(project_id, scope_type).

The authoritative DDL is `schema.sql`. Do not change column names without updating
`query_engine.py` and `seed.py` to match.

---

## 6. Query engine & the read-only guarantee

`query_engine.py` exposes one entry point: `route(question: str) -> {"answer": str}`.
The natural-language question maps to ONE approved query. **Three independent
layers enforce read-only — all three must remain:**

1. **Read-only connection.** DB opened `mode=ro`; writes fail at the engine level.
   PROD equivalent: a least-privilege read-only Azure SQL user.
2. **SELECT-only validator** (`_run`). Single statement, must start with `SELECT`,
   no write/DDL keywords (`insert|update|delete|drop|alter|create|replace|truncate|attach|pragma`).
3. **Pre-approved query library.** Questions route to fixed parameterized queries;
   the NL layer picks *which* approved query + safe params, never free-form SQL.
   This neutralizes prompt-injection / text-to-SQL risk — a malicious instruction
   hidden in a vendor's permit comment still cannot produce a destructive query.

Approved queries (all read-only): `materials_status`, `site_photos`,
`design_assets`, `contract_info`, `shipping_info`, `permit_summary`,
`permit_comment_search`.

**`materials_status` is the centerpiece.** For each in-scope scope it returns
`ordered` / `quoted, not ordered` / `none yet`, and for permit-gated scopes that
aren't ordered it appends the permit status (e.g. "permit-gated — permit is
'pending review'"). This is the "have we ordered materials" answer, correctly
split per scope.

**`permit_comment_search`** is the semantic-search stand-in: ranks comments by
word overlap so the demo runs offline. **PROD:** embed question + comments,
store comment embeddings in `VECTOR(1536)`, rank by cosine similarity.

**NL router (`route`)** is keyword-based for zero-setup offline running. **PROD
swap:** an Anthropic API call classifies intent and extracts (project,
asset_type), but still selects only from the approved query functions and never
emits SQL — so read-only holds regardless of the router.

---

## 7. Streamlit UI to build (`streamlit_app.py`)

**Recommendation: Streamlit.** It wraps the existing `route()` with no rewrite,
gives an interviewer a clickable/typeable interface, and deploys free. Build it
to these requirements:

### Layout
- **Title + one-line subtitle**: "Renovation Project Assistant — ask about any
  site in plain English (read-only)."
- **A read-only badge** somewhere visible (e.g. a small caption or `st.info`)
  stating the assistant can only retrieve data, never change it. This is a
  selling point in the interview — make it visible.
- **Sidebar**: list the 3 sample sites (Warner Robins, Gainesville, Flowery
  Branch) and a short "Try asking…" list of example questions (pull from
  `DEMO_QUESTIONS` in `app.py`). Clicking an example should populate the input.
- **Main panel**: a text input + Ask button. On submit, call
  `query_engine.route(question)` and render `result["answer"]` in an
  `st.markdown` block (preserve line breaks — the answers are multi-line).
- **Optional nicety**: keep a running transcript of Q→A pairs in
  `st.session_state` so the interviewer can see the conversation history.

### Constraints
- Import and call the existing `route()` — **do not** reimplement query logic in
  the Streamlit file. The UI is a thin shell over the engine.
- Do **not** open any writable DB connection from the UI. All data access goes
  through `query_engine`, which is read-only by construction.
- No secrets, no API keys in the demo build (the keyword router needs none).

### Skeleton (Claude Code: flesh this out)
```python
import streamlit as st
from query_engine import route

st.set_page_config(page_title="Renovation Project Assistant", page_icon="🏗️")
st.title("Renovation Project Assistant")
st.caption("Ask about any site in plain English. Read-only — retrieves data, never changes it.")

if "history" not in st.session_state:
    st.session_state.history = []

with st.sidebar:
    st.subheader("Sample sites")
    st.write("- Next Level Petroleum — Warner Robins")
    st.write("- QuikFuel — Gainesville")
    st.write("- Star Mart — Flowery Branch")
    st.subheader("Try asking")
    examples = [
        "Have we ordered materials for the Warner Robins site?",
        "What's the holdup on the Warner Robins sign permit?",
        "Pull up the main ID render for Warner Robins.",
        "Are there any site photos for Flowery Branch?",
    ]
    for ex in examples:
        if st.button(ex, key=ex):
            st.session_state.pending = ex

q = st.text_input("Your question", value=st.session_state.pop("pending", ""))
if st.button("Ask") and q:
    answer = route(q)["answer"]
    st.session_state.history.insert(0, (q, answer))

for question, answer in st.session_state.history:
    st.markdown(f"**> {question}**")
    st.markdown(answer.replace("\n", "  \n"))
    st.divider()
```

---

## 8. Run & deploy

### Local (recommended for interviews)
```
pip install -r requirements.txt     # only streamlit is needed for the UI
python seed.py                       # build the database
streamlit run streamlit_app.py       # opens at http://localhost:8501
```
Most reliable for a live demo: no cold start, no network dependency, you control
the screen.

### Streamlit Community Cloud (optional, for a shareable link)
- Push the repo to GitHub, connect it at share.streamlit.io, set
  `streamlit_app.py` as the entry point.
- Add a startup step (or commit a pre-built `gas_renovation.db`) so `seed.py` has
  run before the app loads.
- Safe to deploy publicly **because the data is synthetic**. Do not deploy a
  version wired to real customer data — those contracts contain PII.

### CLI (quick verification, no UI)
```
python seed.py && python app.py      # type 'demo' for the scripted walkthrough
```

---

## 9. Tier 1 (this demo) vs Tier 2 (production)

| Concern | Demo (this repo) | Production target |
|---|---|---|
| Database | SQLite, local file | Azure SQL Database |
| AI access | `mode=ro` connection | least-privilege read-only SQL user |
| Vector search | word-overlap in app | `VECTOR(1536)` + native vector search |
| NL routing | keyword router | Anthropic API classifier → same approved queries |
| UI / API | Streamlit | Streamlit (or React) front end over a FastAPI service |
| Contract intake | manual upload | manual upload (unchanged) |
| Monday / email / CompanyCam | synthetic seed | API ingestion, or manual links where volume is low |
| Document extraction | n/a (seeded) | Azure AI Document Intelligence, human-in-the-loop confirm |
| Secrets | none | Azure Key Vault |
| Document links | placeholder paths | authenticated / short-lived signed URLs |
| PII handling | synthetic, no risk | encryption at rest (default), access logging, governed access |

Swapping in the LLM router does **not** weaken read-only — layers 1 and 2 sit
underneath regardless.

---

## 10. Acceptance criteria (Claude Code: verify all)

Functional:
1. `python seed.py` builds `gas_renovation.db` with 3 projects, no errors.
2. Warner Robins materials status returns: canopy_forecourt = ordered;
   main_id = quoted, not ordered; signage = quoted, not ordered **with permit
   context**.
3. Gainesville returns both scopes = ordered.
4. Flowery Branch returns both scopes = none yet.
5. "Holdup on the Warner Robins sign permit" returns the permit summary plus the
   "2 to 3 week backlog" comment as top result.
6. "Main ID render for Warner Robins" returns the linked art; a site with no
   asset returns "none yet" cleanly.
7. Flowery Branch site photos returns "none yet."
8. Streamlit app launches, example buttons populate the input, answers render
   with line breaks preserved.

Security (must all pass):
9. `_run("DELETE FROM projects")`, and likewise UPDATE / INSERT / DROP, each
   raise and are refused by the validator.
10. A direct write on the read-only connection
    (`_connect_readonly().execute("DELETE FROM projects")`) raises
    `sqlite3.OperationalError`.
11. A legitimate `SELECT` still returns rows.
12. The Streamlit UI opens no writable connection and reimplements no query logic.

Hygiene:
13. No secrets/API keys committed. `requirements.txt` lists only what's used
    (`streamlit`; `anthropic` only if the LLM router is added).
14. `gas_renovation.db` is a build artifact — not committed; regenerated by
    `seed.py`. Add it to `.gitignore`.

---

## 11. Notes for extending

- To make the router robust to looser phrasing, replace `route()`'s keyword logic
  with an Anthropic API classifier that returns a structured choice of
  {approved_query, project_id, asset_type}. Keep the approved-query library as the
  only thing it can select — never let the model emit SQL.
- To add real Monday.com mirroring, write a small sync that pulls board items +
  updates into `permits` / `permit_updates` on a schedule; keep `monday_item_url`
  so users can click back to the live card.
- If real jobs are often signage-only or canopy-only, `project_scopes` already
  handles it — just flag the scopes that apply. "none yet" only fires for
  in-scope work.
