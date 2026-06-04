# Gas Station Renovation — Project Data System (Scoped Demo)

A working proof of concept for a single source of truth across the renovation
project lifecycle, queryable in plain English. Built to demonstrate the design;
not wired to live systems. Runs offline on SQLite with synthetic data modeled
on a real APEC Imaging and Canopies quote.

## Run it

```
python seed.py      # builds gas_renovation.db with 3 sample projects
python app.py        # interactive; type 'demo' for the scripted walkthrough
```

No dependencies beyond the Python standard library. Python 3.9+.

## What it answers

Ask in plain English and the system retrieves and presents the answer:

- "Have we ordered materials for the Warner Robins site?" — per-scope status,
  answering separately for canopy/forecourt and signage, since they run on
  different clocks.
- "What's the holdup on the Warner Robins sign permit?" — pulls the permit
  status and the most relevant note from the permit person.
- "Pull up the main ID render for Gainesville." — returns the linked art, or
  says none exists yet.
- Plus site photos, shipping dates, and contract lookups.

## The design, in one breath

A signed contract creates a project, which forks into two parallel tracks.
The **permitting track** mirrors Monday.com (status plus the permit person's
free-text notes). The **materials track** gathers quotes, which carry **design
assets** (sign renders, canopy layouts) that flow across to the permit person
to file — the one place the two tracks touch. Materials split into two scopes:
**canopy/forecourt** can be ordered on approval, while **signage** is
**permit-gated** and waits for approval. Ordering flows through to shipment and
receipt, then hands off to scheduling, which is outside this system's boundary.

## Why the pieces are shaped the way they are

**Documents are linked, not stored.** Every `*_path` / `*_url` column points to
a file in storage; the database holds only the queryable facts. Contracts are
uploaded manually (no DocuSign API), with `signed_doc_path` holding the link
and `uploaded_by` recording who did it.

**Controlled vocabularies keep answers trustworthy.** `material_scope`,
`asset_type`, and the order statuses use fixed value sets so that "canopy
layout" and "canopy art" can't silently mean different things. Defining terms so
the data stays trustworthy is the core governance move.

**`project_scopes` makes "none yet" honest.** It declares which scopes a project
actually expects and whether each is permit-gated, flagged manually at signing.
A signage-only job never gets a misleading "canopy: none yet." The flags carry
`set_by` / `set_date` for accountability — if a permit-gate judgment is wrong,
you know who set it and can fix the rule, not just the row.

**One quote PDF, many scope rows.** Real quotes (like the APEC one) bundle
scopes into a single document. The model stores one `quotes` row per scope, all
sharing a `quote_doc_path`, so per-scope status works while honestly recording
that they arrived together.

## Security: the AI is read-only, by design

The query layer can retrieve and present, never modify. Three independent layers
enforce it, verified in testing:

1. **Read-only connection.** The database is opened in `mode=ro`; writes fail at
   the engine level. Production equivalent: a least-privilege read-only Azure SQL
   user. The AI literally cannot write.
2. **SELECT-only validator.** Every query must be a single statement starting
   with `SELECT`, with no write/DDL keywords. Anything else is refused.
3. **Pre-approved query library.** Plain-English questions route to a fixed set
   of parameterized queries. The AI picks *which* approved query to run and fills
   safe parameters — it does not emit free-form SQL. This is what neutralizes
   prompt-injection and text-to-SQL risk: a malicious instruction hidden in, say,
   a vendor's permit comment still can't produce a destructive query.

No system is "100% secure," and the honest framing is that the schema isn't where
vulnerabilities live — the real surface is access control, secrets, link
security, and treating customer PII as governed from day one. The demo addresses
the first; the production notes below address the rest.

## Tier 1 (this demo) vs Tier 2 (production)

| | Demo (here) | Production target |
|---|---|---|
| Database | SQLite, local | Azure SQL Database |
| Vector search | word-overlap in app layer | `VECTOR(1536)` column + native vector search |
| NL routing | keyword router | Anthropic API classifier (still picks from the approved query library only) |
| Contract intake | manual upload | manual upload (unchanged) |
| Monday / email / CompanyCam | synthetic seed data | API ingestion (or manual links where volume is low) |
| Secrets | none needed | Azure Key Vault |
| Document links | placeholder paths | authenticated / short-lived signed URLs |

The keyword router and word-overlap search are deliberate stand-ins so the demo
runs with zero setup. `query_engine.py` marks exactly where each production
component swaps in. Crucially, swapping in an LLM router does not weaken the
read-only guarantee — layers 1 and 2 sit underneath regardless.

## Files

- `schema.sql` — full data model, SQLite with inline `>> PROD:` notes for Azure SQL
- `seed.py` — builds the DB and loads synthetic data
- `query_engine.py` — read-only enforcement, approved query library, NL router
- `app.py` — interactive CLI

## Interview framing

The deliverable a Principal Business Analyst is hired for is the design judgment,
not the deployment. This demo makes that judgment concrete: it shows a messy
operation reduced to a normalized, governed model; a single business question
("have we ordered materials") correctly recognized as several questions on
different clocks; a human placed at the permit-gate decision the source document
can't settle; and an access layer that lets non-analysts self-serve answers
safely. The production tier is the "how I'd take it to scale" half of the story —
and being honest about the credential, security, and adoption work it requires is
itself the maturity the role screens for.
