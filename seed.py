"""
seed.py — build the demo database and load synthetic data.

Run:  python seed.py
Creates gas_renovation.db in this folder (deletes any existing one first).

The data is synthetic but modeled on a real quote (APEC Imaging and Canopies,
Next Level Petroleum, 700 N Davis Dr, Warner Robins GA) plus two contrasting
sites so every materials-status case shows up: ordered, quoted-not-ordered,
and none-yet.
"""

import os
import sqlite3

DB = os.path.join(os.path.dirname(__file__), "gas_renovation.db")
SCHEMA = os.path.join(os.path.dirname(__file__), "schema.sql")


def build():
    if os.path.exists(DB):
        os.remove(DB)
    conn = sqlite3.connect(DB)
    conn.executescript(open(SCHEMA).read())
    cur = conn.cursor()

    # ---- vendors --------------------------------------------------------
    vendors = [
        (1, "APEC Imaging and Canopies", "canopy_forecourt", "info@apecimaging.com"),
        (2, "Dualite", "signage", "quotes@dualite.com"),
        (3, "Federal Heath", "canopy_forecourt", "quotes@federalheath.com"),
        (4, "Big Red Rooster", "canopy_forecourt", "quotes@bigredrooster.com"),
    ]
    cur.executemany("INSERT INTO vendors VALUES (?,?,?,?)", vendors)

    # ---- projects -------------------------------------------------------
    projects = [
        (1, "Next Level Petroleum - Warner Robins", "700 North Davis Drive, Warner Robins, GA 31093",
         "Ali Shan", "Self-performed", "active", "2026-05-12"),
        (2, "QuikFuel - Gainesville", "1200 Jesse Jewell Pkwy, Gainesville, GA 30501",
         "R. Patel", "Self-performed", "active", "2026-03-03"),
        (3, "Star Mart - Flowery Branch", "5500 Atlanta Hwy, Flowery Branch, GA 30542",
         "J. Nguyen", "Self-performed", "planning", "2026-05-20"),
    ]
    cur.executemany("INSERT INTO projects VALUES (?,?,?,?,?,?,?)", projects)

    # ---- contracts (manual upload of signed copy) -----------------------
    contracts = [
        (1, 1, "Ali Shan", 22570.00, "signed", "2026-05-12",
         "sharepoint://contracts/NextLevel_WarnerRobins_signed.pdf", "office.admin"),
        (2, 2, "R. Patel", 19850.00, "signed", "2026-03-03",
         "sharepoint://contracts/QuikFuel_Gainesville_signed.pdf", "office.admin"),
        (3, 3, "J. Nguyen", 17400.00, "signed", "2026-05-20",
         "sharepoint://contracts/StarMart_FloweryBranch_signed.pdf", "office.admin"),
    ]
    cur.executemany("INSERT INTO contracts VALUES (?,?,?,?,?,?,?,?)", contracts)

    # ---- project_scopes (flagged manually at signing) -------------------
    # Project 1: canopy + main_id (reface, NOT gated) + signage (gated). No options.
    # Project 2: canopy + signage (gated). No main_id.
    # Project 3: canopy + signage (gated) but NO quotes yet -> "none yet".
    scopes = [
        # project 1
        (1, 1, "canopy_forecourt", 1, 0, "office.admin", "2026-05-12"),
        (2, 1, "main_id",          1, 0, "office.admin (reface of existing cabinet - exempt)", "2026-05-12"),
        (3, 1, "signage",          1, 1, "office.admin", "2026-05-12"),
        (4, 1, "options",          0, 0, "office.admin", "2026-05-12"),
        # project 2
        (5, 2, "canopy_forecourt", 1, 0, "office.admin", "2026-03-03"),
        (6, 2, "signage",          1, 1, "office.admin", "2026-03-03"),
        # project 3
        (7, 3, "canopy_forecourt", 1, 0, "office.admin", "2026-05-20"),
        (8, 3, "signage",          1, 1, "office.admin", "2026-05-20"),
    ]
    cur.executemany("INSERT INTO project_scopes VALUES (?,?,?,?,?,?,?)", scopes)

    # ---- quotes (one row per scope; shared doc path per source PDF) -----
    quotes = [
        # project 1 - the APEC bundled quote split into scopes
        (1, 1, 1, "canopy_forecourt", 16500.81, "2026-05-14", "sharepoint://quotes/APEC_WarnerRobins.pdf"),
        (2, 1, 1, "main_id",           3500.00, "2026-05-14", "sharepoint://quotes/APEC_WarnerRobins.pdf"),
        (3, 1, 2, "signage",          19687.09, "2026-05-15", "sharepoint://quotes/Dualite_WarnerRobins.pdf"),
        # project 2
        (4, 2, 3, "canopy_forecourt", 18200.00, "2026-03-08", "sharepoint://quotes/FedHeath_Gainesville.pdf"),
        (5, 2, 2, "signage",          14300.00, "2026-03-10", "sharepoint://quotes/Dualite_Gainesville.pdf"),
        # project 3 has NO quotes yet (intentional)
    ]
    cur.executemany("INSERT INTO quotes VALUES (?,?,?,?,?,?,?)", quotes)

    # ---- sales_orders ---------------------------------------------------
    # project 1: canopy ordered; main_id & signage quoted but NOT ordered
    #            (signage waiting on the permit gate).
    # project 2: BOTH canopy and signage ordered (permit approved).
    orders = [
        (1, 1, 1, 1, "canopy_forecourt", "ordered", "2026-05-18", "sharepoint://orders/APEC_WR_SO.pdf"),
        (2, 2, 3, 4, "canopy_forecourt", "ordered", "2026-03-12", "sharepoint://orders/FedHeath_GV_SO.pdf"),
        (3, 2, 2, 5, "signage",          "ordered", "2026-04-25", "sharepoint://orders/Dualite_GV_SO.pdf"),
    ]
    cur.executemany("INSERT INTO sales_orders VALUES (?,?,?,?,?,?,?,?)", orders)

    # ---- shipments ------------------------------------------------------
    shipments = [
        (1, 1, "2026-06-20", None, 0),          # project 1 canopy: expected, not received
        (2, 2, "2026-03-28", "2026-03-27", 1),  # project 2 canopy: received
        (3, 3, "2026-05-30", None, 0),          # project 2 signage: expected
    ]
    cur.executemany("INSERT INTO shipments VALUES (?,?,?,?,?)", shipments)

    # ---- permits --------------------------------------------------------
    permits = [
        (1, 1, "Sign permit", "Houston County", "pending review", "Maria",
         "https://company.monday.com/boards/permits/item/1001", "2026-05-16"),
        (2, 2, "Sign permit", "Hall County", "approved", "Maria",
         "https://company.monday.com/boards/permits/item/1002", "2026-03-20"),
        (3, 3, "Sign permit", "Hall County", "awaiting documents", "Maria",
         "https://company.monday.com/boards/permits/item/1003", None),
    ]
    cur.executemany("INSERT INTO permits VALUES (?,?,?,?,?,?,?,?)", permits)

    # ---- permit_updates (free-text notes -> semantic search target) -----
    updates = [
        (1, 1, "Submitted the sign permit application to Houston County on 5/16. Waiting on plan review.", "Maria", "2026-05-16"),
        (2, 1, "Houston County wants an updated site survey showing the setback from Davis Drive before they approve. Asked the office to send it.", "Maria", "2026-05-19"),
        (3, 1, "Reviewer said there is a 2 to 3 week backlog, so the sign permit is the holdup right now. Cannot order signs until this clears.", "Maria", "2026-05-22"),
        (4, 2, "Hall County approved the sign permit on 4/22. All clear to order signage.", "Maria", "2026-04-22"),
        (5, 3, "Need the signed contract and a site survey before I can start the Flowery Branch permit.", "Maria", "2026-05-21"),
    ]
    cur.executemany("INSERT INTO permit_updates VALUES (?,?,?,?,?)", updates)

    # ---- design_assets (the bridge: vendor -> permit person) ------------
    assets = [
        (1, 1, 2, 3, "main_id_render", "sharepoint://art/Dualite_WR_MainID_render.pdf", "2026-05-15", "Texaco faces, new LED digits"),
        (2, 1, 1, 1, "canopy_layout",  "sharepoint://art/APEC_WR_canopy_layout.pdf",   "2026-05-14", "Red flat facia, 4 sides"),
        (3, 2, 3, 4, "canopy_layout",  "sharepoint://art/FedHeath_GV_canopy_layout.pdf","2026-03-08", None),
        # project 3 has NO design assets yet (intentional)
    ]
    cur.executemany("INSERT INTO design_assets VALUES (?,?,?,?,?,?,?,?)", assets)

    # ---- site_photos (manual CompanyCam links) --------------------------
    photos = [
        (1, 1, "https://app.companycam.com/projects/wr-700davis/photos/1", "Existing canopy, before", "2026-05-13"),
        (2, 1, "https://app.companycam.com/projects/wr-700davis/photos/2", "Main ID sign, current", "2026-05-13"),
        (3, 2, "https://app.companycam.com/projects/gv-jessejewell/photos/1", "Forecourt after paint", "2026-03-29"),
        # project 3 has NO photos yet (intentional)
    ]
    cur.executemany("INSERT INTO site_photos VALUES (?,?,?,?,?)", photos)

    conn.commit()
    conn.close()
    print(f"Built {DB} with 3 projects of synthetic data.")


if __name__ == "__main__":
    build()
