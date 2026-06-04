"""
app.py — interactive demo. Ask questions in plain English.

Run:  python app.py
(Run  python seed.py  first to build the database.)

Type a question, or 'demo' to run the scripted walkthrough, or 'quit'.
"""

import os
import sys
from query_engine import route

DB = os.path.join(os.path.dirname(__file__), "gas_renovation.db")

DEMO_QUESTIONS = [
    "Have we ordered materials for the Warner Robins site?",
    "What about Gainesville — have we ordered materials there?",
    "Have we ordered anything for the Flowery Branch project yet?",
    "What's the holdup on the Warner Robins sign permit?",
    "Pull up the main ID render for Warner Robins.",
    "Are there any site photos for the Flowery Branch site?",
    "When are the canopy materials for Warner Robins expected to ship?",
    "Show me the contract for Gainesville.",
]


def ask(q):
    print(f"\n> {q}")
    try:
        print(route(q)["answer"])
    except Exception as e:
        print(f"[refused] {e}")


def main():
    if not os.path.exists(DB):
        print("Database not found. Run:  python seed.py")
        sys.exit(1)

    print("=" * 68)
    print(" Gas Station Renovation — natural-language demo (READ ONLY)")
    print(" Ask about materials status, permits, photos, art, shipping,")
    print(" or contracts. Type 'demo' for the walkthrough, 'quit' to exit.")
    print("=" * 68)

    while True:
        try:
            q = input("\nask> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q:
            continue
        if q.lower() in ("quit", "exit"):
            break
        if q.lower() == "demo":
            for dq in DEMO_QUESTIONS:
                ask(dq)
            continue
        ask(q)


if __name__ == "__main__":
    main()
