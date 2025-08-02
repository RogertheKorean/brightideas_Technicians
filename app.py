import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, storage
import tempfile
import datetime
from csv_import import csv_import_tab  # Import the CSV import tab

# --- Initialize Firebase with Streamlit secrets ---
if not firebase_admin._apps:
    firebase_creds = dict(st.secrets["firebase"])
    cred = credentials.Certificate(firebase_creds)
    firebase_admin.initialize_app(cred, {
        "storageBucket": "bright-ideas-verify-technician.firebasestorage.app"
    })

db = firestore.client()
bucket = storage.bucket()

# --- Helper Functions ---
def list_technicians():
    techs = db.collection("technicians").stream()
    return [{"id": t.id, **t.to_dict()} for t in techs]

def list_assignments(today_only=True, badge_id=None):
    today = datetime.datetime.now().date()
    assignments = db.collection("assignments").stream()
    out = []
    for doc in assignments:
        a = doc.to_dict()
        a["_id"] = doc.id
        try:
            dt = datetime.datetime.fromisoformat(a["created_at"]).date()
        except Exception:
            continue
        if today_only and dt != today:
            continue
        if badge_id and a["badge_id"] != badge_id:
            continue
        out.append(a)
    return out

def add_assignment(data):
    data["created_at"] = datetime.datetime.now().isoformat()
    db.collection("assignments").add(data)

def verify_assignment(doc_id):
    db.collection("assignments").document(doc_id).update({
        "verified": True,
        "verified_at": datetime.datetime.now().isoformat()
    })

def update_technician(badge_id, tech_data):
    db.collection("technicians").document(badge_id).update(tech_data)

def update_assignment(doc_id, data):
    db.collection("assignments").document(doc_id).update(data)

def export_assignments_csv():
    import pandas as pd
    assignments = db.collection("assignments").stream()
    rows = [doc.to_dict() for doc in assignments]
    if rows:
        df = pd.DataFrame(rows)
        csv = df.to_csv(index=False)
        st.download_button("Download Assignments CSV", csv, "assignments.csv")
    else:
        st.info("No assignments to export.")

# --- Streamlit App Layout ---
query_params = st.query_params
view = query_params.get("view", ["admin"])[0] if isinstance(query_params.get("view", ""), list) else query_params.get("view", "admin")

if view == "admin":
    st.title("Bright Ideas Admin Panel (Firebase Version)")
    tab1, tab2, tab3 = st.tabs(["Technician Manager", "Assign Job", "Bulk CSV Import"])

    # --- Technician Manager ---
    with tab1:
        # (Insert your Technician Manager logic here)
        pass

    # --- Assignment Tab ---
    with tab2:
        # (Insert your Assignment logic here)
        pass

    # --- Bulk CSV Import Tab ---
    with tab3:
        csv_import_tab(db)

elif view == "verify":
    st.title("Customer: Verify Your Technician")
    badge_id = query_params.get("badge_id", [""])[0]
    if not badge_id:
        badge_id = st.text_input("Enter Technician Badge ID to verify jobs for today")
    if badge_id:
        jobs = list_assignments(badge_id=badge_id)
        tech = next((t for t in list_technicians() if t['badge_id'] == badge_id), None)
        if tech:
            st.markdown(
                f"""
                <div style=\"display: flex; align-items: center; background: #f8f9fa; border-radius: 12px; padding: 18px; margin-bottom: 20px; box-shadow: 0 2px 6px rgba(0,0,0,0.07);\">
                  <img src=\"{tech['photo_url']}\" width=\"95\" style=\"border-radius: 16px; margin-right: 24px; border: 2px solid #eee;\">
                  <div>
                    <h3 style=\"margin-bottom: 5px;\">Technician: {tech['name']}</h3>
                    <div style=\"color: #777;\">Badge ID: <b>{badge_id}</b></div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        if not jobs:
            st.warning("No jobs found for this technician today.")
        else:
            st.markdown("### Your Scheduled Service")
            for idx, job in enumerate(jobs):
                with st.container():
                    st.markdown(
                        f"""
                        <div style=\"background: #e9f8ef; border-radius: 10px; padding: 18px 22px; margin-bottom: 18px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);\">
                          <div><b>Customer:</b> {job['customer_name']}</div>
                          <div><b>Address:</b> {job['address']}</div>
                          <div><b>Project #:</b> {job['project_id']}</div>
                          <div><b>Scheduled Time:</b> {job['scheduled_time']}</div>
                          <div><b>Truck:</b> {job['truck_id']}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    colA, colB = st.columns([2,1])
                    with colA:
                        if st.button(f"✅ I Verified (Job {idx+1})"):
                            verify_assignment(job['_id'])
                            st.success("Thank you for verifying your technician!")
                            st.experimental_rerun()
                    with colB:
                        with st.expander("Show full details"):
                            st.json(job)
            st.caption("If you have multiple scheduled jobs, verify each one separately.")
    st.caption("For best experience, view on mobile or desktop.")

else:
    st.error("Unknown view. Use ?view=admin or ?view=verify in the URL.")
