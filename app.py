# app.py
import streamlit as st
import pandas as pd
from db import query_all, query_one, execute, get_next_id,get_conn
from utils import hash_password, check_password
import mysql.connector
from mysql.connector import IntegrityError, Error
import datetime


st.set_page_config(page_title="E-Voting System (India)", layout="wide")

PAGES = ["Home", "Register Citizen", "Register Voter", "Register Candidate",
         "Change assembly", "Voter Login & Vote", "Results", "Admin: View Tables"]

page = st.sidebar.selectbox("Navigation", PAGES)

def home():
    st.title("E-Voting System — Demo")
    st.markdown("Use the sidebar to navigate. This demo maps to your `voting_system` schema.")

def register_citizen():
    st.header("Register Citizen")
    with st.form("citizen_form"):
        name = st.text_input("Full name")
        address = st.text_area("Address")
        phone = st.text_input("Phone number")
        min_date = datetime.date(1900, 1, 1)   # oldest allowed DOB
        max_date = datetime.date.today()       # latest allowed DOB

        dob = st.date_input(
    "Date of birth",
    value=datetime.date(2000, 1, 1),   # default value shown
    min_value=min_date,
    max_value=max_date
)
        aadhar = st.text_input("Aadhar")
        submitted = st.form_submit_button("Create Citizen")
        if submitted:
            if not name or not aadhar:
                st.error("Name and Aadhar are required")
            else:
                try:
                    cid = get_next_id("Citizen", "citizen_id")
                    sql = """INSERT INTO Citizen (citizen_id, name, address, phone_number, dob, aadhar)
                             VALUES (%s,%s,%s,%s,%s,%s)"""
                    execute(sql, (cid, name, address, phone, dob, aadhar))
                    st.success(f"Citizen created with citizen_id = {cid}")
                except Exception as e:
                    st.error(f"DB error: {e}")

def register_voter():
    st.header("Register Voter (from Citizen)")

    # Load citizens
    citizens = query_all("SELECT citizen_id, name, aadhar FROM Citizen")
    if not citizens:
        st.info("No citizens yet. Register a citizen first.")
        return

    # build selectbox options
    map_opts = {f"{c['citizen_id']}: {c['name']} ({c['aadhar']})": c['citizen_id'] for c in citizens}
    sel = st.selectbox("Choose citizen to register as voter", list(map_opts.keys()))
    citizen_id = map_opts[sel]

    # get password (plain)
    password = st.text_input("Set voter password (plaintext will be stored)", type="password")

    # booths list (optional assignment)
    booths = query_all("SELECT booth_id, booth_name FROM Booth")
    booth_map = {f"{b['booth_id']}: {b['booth_name']}": b['booth_id'] for b in booths}
    booth_sel = st.selectbox("Assign booth (optional)", ["None"] + list(booth_map.keys()))

    if st.button("Create voter record"):
        # basic validation
        if not password:
            st.error("Password is required for voter account")
            return

        try:
            # fetch citizen details
            c = query_one("SELECT citizen_id, name, dob, address, aadhar FROM Citizen WHERE citizen_id = %s", (citizen_id,))
            if not c:
                st.error("Selected citizen not found.")
                return

            # determine booth_id or NULL
            booth_id = None if booth_sel == "None" else booth_map[booth_sel]

            # generate voter_id (uses your get_next_id since your schema likely has no AUTO_INCREMENT)
            v_id = get_next_id("Voter", "voter_id")

            # Insert into Voter — include password column and has_voted (0)
            sql = """
                INSERT INTO Voter
                  (voter_id, citizen_id, name, dob, addressname, aadhar, booth_id, password, has_voted)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            params = (
                v_id,
                c['citizen_id'],
                c.get('name'),
                c.get('dob'),
                c.get('address'),
                c.get('aadhar'),
                booth_id,
                password,   # plaintext password stored as requested
                0           # has_voted default = 0
            )

            # execute insert
            execute(sql, params)

            st.success(f"Voter created with voter_id = {v_id}")
            st.info("Reminder: password stored in plaintext in DB (not secure).")
        except Exception as e:
            st.error(f"DB error: {e}")
            return


def register_candidate():
    st.header("Register Candidate")
    citizens = query_all("SELECT citizen_id, name FROM Citizen")
    voters = query_all("SELECT voter_id, name FROM Voter")
    assemblies = query_all("SELECT assembly_id, assembly_name FROM Assembly")
    with st.form("candidate_form"):
        name = st.text_input("Candidate name")
        citizen_choice = st.selectbox("Citizen (optional)", ["None"] + [f"{c['citizen_id']}: {c['name']}" for c in citizens])
        voter_choice = st.selectbox("Voter (optional)", ["None"] + [f"{v['voter_id']}: {v['name']}" for v in voters])
        assembly_choice = st.selectbox("Assembly", ["None"] + [f"{a['assembly_id']}: {a['assembly_name']}" for a in assemblies])
        submitted = st.form_submit_button("Register candidate")
        if submitted:
            citizen_id = None if citizen_choice == "None" else int(citizen_choice.split(":")[0])
            voter_id = None if voter_choice == "None" else int(voter_choice.split(":")[0])
            assembly_id = None if assembly_choice == "None" else int(assembly_choice.split(":")[0])
            try:
                cand_id = get_next_id("Candidate", "candidate_id")
                sql = """INSERT INTO Candidate (candidate_id, citizen_id, voter_id, assembly_id, name)
                         VALUES (%s,%s,%s,%s,%s)"""
                execute(sql, (cand_id, citizen_id, voter_id, assembly_id, name))
                st.success(f"Candidate registered with candidate_id = {cand_id}")
            except Exception as e:
                st.error(f"DB error: {e}")

# make sure these are imported at top of app.py:
# from db import query_one, query_all, execute

def change_assembly():
    st.header("Change Assembly / Reassign Booth")

    # --- Step 0: inputs for lookup ---
    voter_id_input = st.text_input("Enter your Voter ID (to change assembly):", key="ca_voter_id")
    aadhar_input = st.text_input("Enter your Aadhaar Number:", key="ca_aadhar")

    if st.button("Lookup Voter", key="ca_lookup"):
        if not voter_id_input or not aadhar_input:
            st.error("Please enter both Voter ID and Aadhaar.")
        else:
            try:
                voter = query_one(
                    """SELECT v.voter_id, v.name, v.booth_id, v.has_voted,
                              b.booth_name, b.assembly_id, a.assembly_name
                       FROM Voter v
                       LEFT JOIN Booth b ON v.booth_id = b.booth_id
                       LEFT JOIN Assembly a ON b.assembly_id = a.assembly_id
                       WHERE v.voter_id = %s AND v.aadhar = %s""",
                    (voter_id_input, aadhar_input)
                )
            except Exception as e:
                st.error(f"DB error while looking up voter: {e}")
                voter = None

            if not voter:
                st.error("Invalid Voter ID or Aadhaar.")
                st.session_state.pop("ca_voter", None)
            else:
                if int(voter.get("has_voted", 0)) == 1:
                    st.warning("You have already voted — assembly/booth change is not allowed.")
                    st.session_state.pop("ca_voter", None)
                else:
                    st.success(f"Hello {voter.get('name')}. Lookup successful.")
                    st.session_state["ca_voter"] = {
                        "voter_id": voter.get("voter_id"),
                        "name": voter.get("name"),
                        "booth_id": voter.get("booth_id"),
                        "booth_name": voter.get("booth_name"),
                        "assembly_id": voter.get("assembly_id"),
                        "assembly_name": voter.get("assembly_name"),
                        "has_voted": voter.get("has_voted")
                    }

    if "ca_voter" not in st.session_state:
        return

    ca_voter = st.session_state["ca_voter"]
    cur_booth = ca_voter.get("booth_name") or "Not assigned"
    cur_assembly = ca_voter.get("assembly_name") or "Not assigned"
    st.info(f"Current assignment: Booth: {cur_booth} — Assembly: {cur_assembly}")

    # --- Step 2: choose new assembly ---
    try:
        assemblies = query_all("SELECT assembly_id, assembly_name FROM Assembly ORDER BY assembly_name")
    except Exception as e:
        st.error(f"DB error while fetching assemblies: {e}")
        return

    if not assemblies:
        st.error("No assemblies available in the system.")
        return

    assembly_options = [f"{a['assembly_id']}: {a['assembly_name']}" for a in assemblies]
    sel_assembly_label = st.selectbox("Choose new Assembly", assembly_options, key="ca_sel_assembly")

    try:
        new_assembly_id = int(sel_assembly_label.split(":")[0])
    except Exception:
        st.error("Failed to parse selected assembly. Try again.")
        return

    # --- Step 3: choose booth ---
    try:
        booths = query_all(
            "SELECT booth_id, booth_name FROM Booth WHERE assembly_id = %s ORDER BY booth_name",
            (new_assembly_id,)
        )
    except Exception as e:
        st.error(f"DB error while fetching booths: {e}")
        return

    if not booths:
        st.warning("No booths found for the selected assembly. You can still set booth to Unassigned (NULL).")
        booth_options = ["Unassigned"]
        booth_map = {}
    else:
        booth_map = {f"{b['booth_id']}: {b['booth_name']}": b['booth_id'] for b in booths}
        booth_options = ["Choose a booth", "Unassigned"] + list(booth_map.keys())

    booth_sel = st.selectbox("Choose Booth (optional)", booth_options, key="ca_sel_booth")

    # --- Confirm and update ---
    if st.button("Confirm Change Assembly / Assign Booth", key="ca_confirm"):
        if booth_sel == "Choose a booth":
            st.error("Please select a booth or choose 'Unassigned'.")
            return

        if booth_sel == "Unassigned":
            chosen_booth_id = None
        else:
            chosen_booth_id = booth_map.get(booth_sel)

        try:
            voter_id_db = int(ca_voter["voter_id"])
        except Exception:
            voter_id_db = ca_voter["voter_id"]

        try:
            chosen_booth_id_db = None if chosen_booth_id is None else int(chosen_booth_id)
        except Exception:
            chosen_booth_id_db = chosen_booth_id

        conn = None
        cur = None
        try:
            conn = get_conn()
            conn.start_transaction()
            cur = conn.cursor()

            cur.execute("UPDATE Voter SET booth_id = %s WHERE voter_id = %s", (chosen_booth_id_db, voter_id_db))
            conn.commit()

            if cur.rowcount == 0:
                st.warning("No rows were updated. Please check the Voter ID.")
                conn.rollback()
            else:
                if chosen_booth_id_db is None:
                    new_booth_name = "Unassigned"
                    new_assembly_name = sel_assembly_label.split(": ", 1)[1]
                else:
                    b_row = query_one(
                        "SELECT b.booth_name, a.assembly_name FROM Booth b LEFT JOIN Assembly a ON b.assembly_id = a.assembly_id WHERE b.booth_id = %s",
                        (chosen_booth_id_db,)
                    )
                    new_booth_name = b_row.get("booth_name") if b_row else str(chosen_booth_id_db)
                    new_assembly_name = b_row.get("assembly_name") if b_row and b_row.get("assembly_name") else sel_assembly_label.split(": ", 1)[1]

                st.success("✅ Your assembly/booth assignment has been updated.")
                st.info(f"New assignment: Booth: {new_booth_name} — Assembly: {new_assembly_name}")

                st.session_state["ca_voter"]["booth_id"] = chosen_booth_id_db
                st.session_state["ca_voter"]["booth_name"] = None if chosen_booth_id_db is None else new_booth_name
                st.session_state["ca_voter"]["assembly_id"] = new_assembly_id
                st.session_state["ca_voter"]["assembly_name"] = new_assembly_name

        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            st.error(f"Failed to update assignment: {e}")
        finally:
            if cur:
                try:
                    cur.close()
                except Exception:
                    pass
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass



def voter_login_and_vote():
    st.subheader("Voter Login")

    # --- LOGIN STAGE (persist state so Streamlit reruns don't lose it) ---
    if "voter" not in st.session_state:
        # show login inputs
        voter_id_input = st.text_input("Enter your Voter ID:")
        aadhar_input = st.text_input("Enter your Aadhaar Number:")
        if st.button("Login"):
            if not voter_id_input or not aadhar_input:
                st.error("Please enter both Voter ID and Aadhaar.")
                return

            # fetch voter
            try:
                voter = query_one(
                    "SELECT voter_id, name, booth_id, has_voted, aadhar FROM Voter WHERE voter_id = %s AND aadhar = %s",
                    (voter_id_input, aadhar_input)
                )
            except Exception as e:
                st.error(f"DB error while looking up voter: {e}")
                return

            if not voter:
                st.error("Invalid Voter ID or Aadhaar number.")
                return

            # check flag
            if int(voter.get("has_voted", 0)) == 1:
                st.warning("You have already voted. Multiple votes are not allowed.")
                return

            # fetch booth -> assembly
            try:
                booth_row = query_one("SELECT assembly_id FROM Booth WHERE booth_id = %s", (voter["booth_id"],))
            except Exception as e:
                st.error(f"DB error while fetching booth: {e}")
                return

            if not booth_row:
                st.error("Booth not found for this voter. Contact admin.")
                return

            # persist useful things in session_state
            st.session_state.voter = voter
            st.session_state.assembly_id = int(booth_row["assembly_id"])
            st.success(f"Welcome, {voter['name']}! You are voting in Assembly ID: {st.session_state.assembly_id}")

            # fetch candidates and persist
            try:
                sql = """
                    SELECT c.candidate_id, c.name, c.party_name, c.symbol_image
                    FROM Candidate c
                    WHERE c.assembly_id = %s
                    ORDER BY c.name
                """
                candidates = query_all(sql, (st.session_state.assembly_id,))
            except Exception as e:
                st.error(f"DB error while fetching candidates: {e}")
                # clear session state to allow re-login
                st.session_state.pop("voter", None)
                st.session_state.pop("assembly_id", None)
                return

            if not candidates:
                st.warning("No candidates found for your assembly.")
                st.session_state.pop("voter", None)
                st.session_state.pop("assembly_id", None)
                return

            st.session_state.candidates = candidates
            # initialize a selection placeholder so radio persists
            st.session_state.selected_option = None
        else:
            return  # no login click yet

    # --- VOTING STAGE (user is logged in) ---
    voter = st.session_state.get("voter")
    candidates = st.session_state.get("candidates", [])
    if not voter or not candidates:
        st.error("Internal error: missing voter or candidates. Please login again.")
        st.session_state.pop("voter", None)
        st.session_state.pop("candidates", None)
        return

    st.subheader("Candidates Available for Your Assembly")
    for c in candidates:
        with st.container():
            st.markdown(f"### 🧾 {c['name']}")
            st.write(f"**Party:** {c.get('party_name', 'Independent')}")
            if c.get('symbol_image'):
                st.image(c['symbol_image'], width=100)
            st.markdown("---")

    # radio selection that persists via session_state
    options = [f"{c['candidate_id']}: {c['name']}" for c in candidates]
    if "selected_option" not in st.session_state or st.session_state.selected_option not in options:
        st.session_state.selected_option = options[0]  # default
    st.session_state.selected_option = st.radio("Select your candidate:", options, index=options.index(st.session_state.selected_option))

    # Cast vote button
    if st.button("🗳️ Cast My Vote"):
        try:
            candidate_id = int(st.session_state.selected_option.split(":")[0])
        except Exception:
            st.error("Failed to parse selected candidate. Try again.")
            return

        # Convert ids
        try:
            voter_id_int = int(voter["voter_id"])
            booth_id_int = int(voter["booth_id"])
        except Exception:
            st.error("Internal error: invalid voter_id or booth_id.")
            return

        conn = None
        cur = None
        try:
            # use same DB connection object for the whole transaction
            conn = get_conn()
            conn.start_transaction()
            cur = conn.cursor()

            # lock the voter row to re-check has_voted
            cur.execute("SELECT has_voted FROM Voter WHERE voter_id = %s FOR UPDATE", (voter_id_int,))
            row = cur.fetchone()
            if not row:
                conn.rollback()
                st.error("Voter record not found (unexpected). Aborting.")
                # clear session so user can login again
                st.session_state.pop("voter", None)
                st.session_state.pop("candidates", None)
                return
            if int(row[0]) == 1:
                conn.rollback()
                st.warning("You have already voted. Aborting.")
                st.session_state.pop("voter", None)
                st.session_state.pop("candidates", None)
                return

            # Determine vote_id inside same transaction (if Vote.vote_id is NOT AUTO_INCREMENT)
            # Preferred: if Vote.vote_id is AUTO_INCREMENT, skip this block and use cur.lastrowid after insert.
            cur.execute("SELECT MAX(vote_id) FROM Vote FOR UPDATE")
            max_row = cur.fetchone()
            next_vote_id = (int(max_row[0]) + 1) if (max_row and max_row[0] is not None) else 1

            # Insert vote
            insert_sql = "INSERT INTO Vote (vote_id, voter_id, candidate_id, booth_id) VALUES (%s, %s, %s, %s)"
            cur.execute(insert_sql, (next_vote_id, voter_id_int, candidate_id, booth_id_int))

            # Update voter has_voted
            cur.execute("UPDATE Voter SET has_voted = 1 WHERE voter_id = %s", (voter_id_int,))

            # commit
            conn.commit()

            st.success("✅ Your vote has been successfully recorded!")
            # cleanup session state so user can't re-cast in same browser session
            st.session_state.pop("voter", None)
            st.session_state.pop("candidates", None)
            st.session_state.pop("selected_option", None)
        except IntegrityError as ie:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            # likely duplicate vote insertion or FK violation
            st.warning("It looks like this voter has already voted (DB prevented duplicate) or constraints violated.")
            print("IntegrityError:", ie)
            # cleanup session
            st.session_state.pop("voter", None)
            st.session_state.pop("candidates", None)
        except Error as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            st.error(f"Database error while recording vote: {e}")
            print("DB Error:", e)
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            st.error(f"Unexpected error: {e}")
            import traceback; traceback.print_exc()
        finally:
            if cur:
                try:
                    cur.close()
                except Exception:
                    pass
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass



def results():
    st.header("Results by Assembly")
    assemblies = query_all("SELECT assembly_id, assembly_name FROM Assembly")
    for a in assemblies:
        st.subheader(a['assembly_name'])
        sql = """
            SELECT c.candidate_id, c.name,
                   COUNT(v.vote_id) AS votes
            FROM Candidate c
            LEFT JOIN Vote v ON c.candidate_id = v.candidate_id
            WHERE c.assembly_id = %s
            GROUP BY c.candidate_id, c.name
            ORDER BY votes DESC
        """
        rows = query_all(sql, (a['assembly_id'],))
        df = pd.DataFrame(rows)
        if df.empty:
            st.write("No candidates/votes yet.")
        else:
            st.dataframe(df)

def admin_view_tables():
    st.header("Admin: View tables (read-only)")
    table = st.selectbox("Choose table", ["Citizen", "Voter", "Candidate", "Booth", "Vote", "Assembly", "MLA_MP", "Winner"])
    rows = query_all(f"SELECT * FROM {table} LIMIT 1000")
    df = pd.DataFrame(rows)
    st.dataframe(df)

# Router
if page == "Home":
    home()
elif page == "Register Citizen":
    register_citizen()
elif page == "Register Voter":
    register_voter()
elif page == "Register Candidate":
    register_candidate()
elif page == "Change assembly":
    change_assembly()
elif page == "Voter Login & Vote":
    voter_login_and_vote()
elif page == "Results":
    results()
elif page == "Admin: View Tables":
    admin_view_tables()
