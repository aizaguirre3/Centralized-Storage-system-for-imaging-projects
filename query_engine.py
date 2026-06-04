"""
query_engine.py — the natural-language query layer.

SECURITY: the AI can only RETRIEVE, never modify. Three layers enforce this:

  1. Read-only DB connection.  The database is opened in mode=ro, so any
     INSERT/UPDATE/DELETE fails at the SQLite level. In production this is a
     read-only Azure SQL user (least privilege) — the AI literally cannot write.

  2. SELECT-only validator.  Every query is checked: single statement, must
     start with SELECT, no write keywords. Anything else is refused.

  3. Pre-approved query library.  Natural-language questions are routed to a
     fixed set of parameterized queries (below). The AI chooses WHICH approved
     query to run and fills in safe parameters — it does NOT write free-form
     SQL. This is what neutralizes prompt-injection / text-to-SQL risk.

The NL router here uses keyword patterns so the demo runs offline. The
docstring on `route()` shows exactly where an LLM classifier drops in for
production (it would still only pick from the same approved query library).
"""

import re
import sqlite3
import os

DB = os.path.join(os.path.dirname(__file__), "gas_renovation.db")

WRITE_WORDS = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|truncate|attach|pragma)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
#  Layers 1 & 2: read-only connection + SELECT-only validation
# ---------------------------------------------------------------------------
def _connect_readonly():
    # mode=ro => the connection physically cannot write.
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def _run(sql, params=()):
    if sql.strip().count(";") > 1:
        raise ValueError("Refused: only a single statement is allowed.")
    if not sql.strip().lower().startswith("select"):
        raise ValueError("Refused: only SELECT queries are allowed.")
    if WRITE_WORDS.search(sql):
        raise ValueError("Refused: query contains a write/DDL keyword.")
    conn = _connect_readonly()
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
#  Helper: resolve a project from free text
# ---------------------------------------------------------------------------
def resolve_project(text):
    """Match a question against known projects by id, name, or address tokens."""
    rows = _run("SELECT project_id, site_name, site_address FROM projects")
    t = text.lower()
    m = re.search(r"project\s*#?\s*(\d+)", t)
    if m:
        pid = int(m.group(1))
        for r in rows:
            if r["project_id"] == pid:
                return r
    for r in rows:
        hay = (r["site_name"] + " " + r["site_address"]).lower()
        # match on any distinctive 4+ char token shared between question and project
        for token in re.findall(r"[a-z]{4,}", hay):
            if token in t and token not in ("petroleum", "north", "drive", "atlanta", "self"):
                return r
    return None


# ---------------------------------------------------------------------------
#  Layer 3: the pre-approved query library
# ---------------------------------------------------------------------------

def materials_status(project_id):
    """Per-scope ordered/quoted/none, only for in-scope scopes, with permit
    context on gated scopes. This is the 'have we ordered materials' answer."""
    scopes = _run(
        "SELECT scope_type, is_permit_gated FROM project_scopes "
        "WHERE project_id=? AND in_scope=1 ORDER BY scope_type",
        (project_id,),
    )
    permit = _run(
        "SELECT status FROM permits WHERE project_id=? ORDER BY permit_id LIMIT 1",
        (project_id,),
    )
    permit_status = permit[0]["status"] if permit else "no permit on file"

    results = []
    for s in scopes:
        scope = s["scope_type"]
        ordered = _run(
            "SELECT COUNT(*) n FROM sales_orders "
            "WHERE project_id=? AND material_scope=? AND status='ordered'",
            (project_id, scope),
        )[0]["n"]
        quoted = _run(
            "SELECT COUNT(*) n FROM quotes WHERE project_id=? AND material_scope=?",
            (project_id, scope),
        )[0]["n"]
        if ordered > 0:
            state = "ordered"
        elif quoted > 0:
            state = "quoted, not ordered"
        else:
            state = "none yet"
        note = ""
        if s["is_permit_gated"] and state != "ordered":
            note = f" (permit-gated — permit is '{permit_status}')"
        results.append({"scope": scope, "state": state, "note": note})
    return results


def site_photos(project_id):
    return _run(
        "SELECT companycam_url, caption, date_added FROM site_photos "
        "WHERE project_id=? ORDER BY date_added",
        (project_id,),
    )


def design_assets(project_id, asset_type=None):
    if asset_type:
        return _run(
            "SELECT asset_type, asset_url, notes, received_date FROM design_assets "
            "WHERE project_id=? AND asset_type=? ORDER BY received_date",
            (project_id, asset_type),
        )
    return _run(
        "SELECT asset_type, asset_url, notes, received_date FROM design_assets "
        "WHERE project_id=? ORDER BY received_date",
        (project_id,),
    )


def contract_info(project_id):
    return _run(
        "SELECT customer_name, labor_amount, status, signed_date, signed_doc_path "
        "FROM contracts WHERE project_id=?",
        (project_id,),
    )


def shipping_info(project_id):
    return _run(
        "SELECT so.material_scope, sh.expected_date, sh.actual_date, sh.received "
        "FROM shipments sh JOIN sales_orders so ON sh.order_id=so.order_id "
        "WHERE so.project_id=? ORDER BY sh.expected_date",
        (project_id,),
    )


def permit_summary(project_id):
    return _run(
        "SELECT permit_type, jurisdiction, status, assigned_to, monday_item_url "
        "FROM permits WHERE project_id=?",
        (project_id,),
    )


def permit_comment_search(project_id, question):
    """App-layer semantic search stand-in. Production: embed the question and
    the comments, store comment embeddings in Azure SQL VECTOR(1536), and rank
    by cosine similarity. Here we rank by simple word overlap so it runs offline."""
    rows = _run(
        "SELECT pu.comment_text, pu.author, pu.comment_date "
        "FROM permit_updates pu JOIN permits p ON pu.permit_id=p.permit_id "
        "WHERE p.project_id=?",
        (project_id,),
    )
    q_words = set(re.findall(r"[a-z]{4,}", question.lower()))
    scored = []
    for r in rows:
        c_words = set(re.findall(r"[a-z]{4,}", r["comment_text"].lower()))
        overlap = len(q_words & c_words)
        scored.append((overlap, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    # return the most relevant comments (fall back to most recent if no overlap)
    return [r for score, r in scored[:2]]


# ---------------------------------------------------------------------------
#  NL router: question -> approved query
# ---------------------------------------------------------------------------
def route(question):
    """Map a plain-English question to ONE approved query.

    PRODUCTION SWAP: replace this keyword logic with an Anthropic API call that
    classifies intent and extracts (project, asset_type) — but the model still
    only selects from the approved query functions above and never emits SQL.
    Read-only stays guaranteed because layers 1 & 2 sit underneath regardless.
    """
    q = question.lower()
    proj = resolve_project(question)
    if not proj:
        return {"answer": "Which site? I couldn't tell which project you mean."}
    pid, name = proj["project_id"], proj["site_name"]

    # photos
    if any(w in q for w in ["photo", "pics", "picture", "companycam", "image"]):
        rows = site_photos(pid)
        if not rows:
            return {"answer": f"No site photos for {name} yet."}
        lines = [f"  - {r['caption']}: {r['companycam_url']}" for r in rows]
        return {"answer": f"Site photos for {name}:\n" + "\n".join(lines)}

    # design art / renders / layouts
    if any(w in q for w in ["render", "art", "layout", "drawing", "design"]):
        atype = None
        if "main" in q or "id render" in q:
            atype = "main_id_render"
        elif "canopy" in q:
            atype = "canopy_layout"
        elif "monument" in q:
            atype = "monument_sign"
        rows = design_assets(pid, atype)
        label = atype or "design assets"
        if not rows:
            return {"answer": f"No {label} for {name} yet."}
        lines = [f"  - {r['asset_type']}: {r['asset_url']}" + (f"  [{r['notes']}]" if r['notes'] else "") for r in rows]
        return {"answer": f"{label} for {name}:\n" + "\n".join(lines)}

    # permit holdup / blocking -> summary + comment search
    if any(w in q for w in ["permit", "holdup", "hold up", "blocking", "blocked", "holding"]):
        summary = permit_summary(pid)
        comments = permit_comment_search(pid, question)
        out = []
        if summary:
            s = summary[0]
            out.append(f"{name} permit: {s['permit_type']} in {s['jurisdiction']} — status '{s['status']}' (handled by {s['assigned_to']}).")
        if comments:
            out.append("Most relevant notes:")
            for c in comments:
                out.append(f"  - ({c['comment_date']}, {c['author']}) {c['comment_text']}")
        return {"answer": "\n".join(out) if out else f"No permit on file for {name}."}

    # contract
    if any(w in q for w in ["contract", "signed", "signature"]):
        rows = contract_info(pid)
        if not rows:
            return {"answer": f"No contract on file for {name}."}
        c = rows[0]
        return {"answer": f"{name} contract: {c['status']}, labor ${c['labor_amount']:,.2f}, "
                          f"signed {c['signed_date']}. Signed copy: {c['signed_doc_path']}"}

    # shipping / delivery
    if any(w in q for w in ["ship", "delivery", "deliver", "arrive", "expected", "receive"]):
        rows = shipping_info(pid)
        if not rows:
            return {"answer": f"No shipments tracked for {name} yet."}
        lines = []
        for r in rows:
            if r["received"]:
                lines.append(f"  - {r['material_scope']}: received {r['actual_date']}")
            else:
                lines.append(f"  - {r['material_scope']}: expected {r['expected_date']}, not yet received")
        return {"answer": f"Shipping for {name}:\n" + "\n".join(lines)}

    # default: materials / order status
    rows = materials_status(pid)
    if not rows:
        return {"answer": f"No scopes flagged for {name}."}
    lines = [f"  - {r['scope']}: {r['state']}{r['note']}" for r in rows]
    return {"answer": f"Materials status for {name}:\n" + "\n".join(lines)}
