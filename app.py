import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, storage
import tempfile
import datetime
import pytz
from csv_import import csv_import_tab  # Import the CSV import tab

# --- California Timezone ---
CA_TZ = pytz.timezone('America/Los_Angeles')

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

def list_assignments(for_date=None, badge_id=None):
    if for_date is None:
        for_date = datetime.datetime.now(CA_TZ).strftime("%Y-%m-%d")
    assignments = db.collection("assignments").stream()
    out = []
    for doc in assignments:
        a = doc.to_dict()
        a["_id"] = doc.id
        if a.get("service_date") != for_date:
            continue
        if badge_id and str(a.get("badge_id", "")) != str(badge_id):
            continue
        out.append(a)
    return out


def add_assignment(data):
    now_ca = datetime.datetime.now(CA_TZ)
    data["created_at"] = now_ca.isoformat()
    data["service_date"] = now_ca.strftime("%Y-%m-%d")
    db.collection("assignments").add(data)

def verify_assignment(doc_id):
    now_ca = datetime.datetime.now(CA_TZ)
    db.collection("assignments").document(doc_id).update({
        "verified": True,
        "verified_at": now_ca.isoformat()
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
        st.header("Add/Edit Technician with Photo Upload")
        edit_mode = st.session_state.get('edit_mode', False)
        edit_badge = st.session_state.get('edit_badge', "")
        techs = list_technicians()
        if edit_mode and edit_badge:
            tech = next((t for t in techs if t["badge_id"] == edit_badge), None)
            with st.form("edit_tech"):
                tech_name = st.text_input("Technician Name", value=tech["name"])
                photo_file = st.file_uploader("Upload Technician Photo (optional)", type=["jpg","jpeg","png"])
                submit_edit = st.form_submit_button("Update Technician")
                if submit_edit:
                    update = {"name": tech_name}
                    if photo_file:
                        temp_file = tempfile.NamedTemporaryFile(delete=False)
                        temp_file.write(photo_file.read())
                        temp_file.close()
                        blob = bucket.blob(f"technician_photos/{edit_badge}_{photo_file.name}")
                        with open(temp_file.name, "rb") as img_file:
                            blob.upload_from_file(img_file)
                        blob.make_public()
                        photo_url = blob.public_url
                        update["photo_url"] = photo_url
                    update_technician(edit_badge, update)
                    st.success(f"Technician {tech_name} updated!")
                    st.session_state.edit_mode = False
                    st.rerun()
            st.button("Cancel Edit", on_click=lambda: st.session_state.update({'edit_mode': False}))
        else:
            with st.form("add_tech"):
                tech_name = st.text_input("Technician Name")
                badge_id = st.text_input("Badge ID")
                photo_file = st.file_uploader("Upload Technician Photo", type=["jpg", "jpeg", "png"])
                submitted = st.form_submit_button("Add Technician")
                if submitted:
                    if not (tech_name and badge_id and photo_file):
                        st.error("All fields required.")
                    else:
                        temp_file = tempfile.NamedTemporaryFile(delete=False)
                        temp_file.write(photo_file.read())
                        temp_file.close()
                        blob = bucket.blob(f"technician_photos/{badge_id}_{photo_file.name}")
                        with open(temp_file.name, "rb") as img_file:
                            blob.upload_from_file(img_file)
                        blob.make_public()
                        photo_url = blob.public_url
                        tech_data = {
                            "name": tech_name,
                            "badge_id": badge_id,
                            "photo_url": photo_url,
                        }
                        db.collection("technicians").document(badge_id).set(tech_data)
                        st.success(f"Technician {tech_name} added with photo!")
                        st.image(photo_url, width=200, caption="Uploaded Photo")
                        st.write("Photo URL:", photo_url)
            st.session_state.edit_mode = False

        st.subheader("All Technicians in Database")
        for d in techs:
            st.write(f"👷 {d['name']} ({d['badge_id']})")
            st.image(d['photo_url'], width=120)
            cols = st.columns(3)
            if cols[0].button(f"Edit {d['badge_id']}"):
                st.session_state.edit_mode = True
                st.session_state.edit_badge = d['badge_id']
                st.rerun()
            if cols[1].button(f"Delete {d['badge_id']}"):
                db.collection("technicians").document(d['badge_id']).delete()
                st.success(f"Deleted technician {d['badge_id']}")
                st.rerun()
            cols[2].markdown(f"[Copy Photo Link](javascript:navigator.clipboard.writeText('{d['photo_url']}'))")

    # --- Assignment Tab ---
    with tab2:
        st.header("Assign/Edit Job to Technician")
        # Date filter for assignments
        selected_date = st.date_input("Show assignments for date (California time)", value=datetime.datetime.now(CA_TZ).date())
        selected_date_str = selected_date.strftime("%Y-%m-%d")

        edit_job = st.session_state.get('edit_job', False)
        edit_job_id = st.session_state.get('edit_job_id', "")
        techs = list_technicians()
        if edit_job and edit_job_id:
            assignments = list_assignments(for_date=selected_date_str)
            a = next((x for x in assignments if x['_id'] == edit_job_id), None)
            with st.form("edit_job_form"):
                tech_options = [f"{t['name']} ({t['badge_id']})" for t in techs]
                tech_idx = st.selectbox("Technician", options=range(len(tech_options)), format_func=lambda i: tech_options[i], index=next((i for i,t in enumerate(techs) if t["badge_id"]==a["badge_id"]), 0))
                customer_name = st.text_input("Customer Name", value=a['customer_name'])
                address = st.text_input("Address", value=a['address'])
                project_id = st.text_input("Project ID", value=a['project_id'])
                scheduled_time = st.time_input("Scheduled Time", datetime.datetime.strptime(a['scheduled_time'], "%H:%M").time())
                truck_id = st.text_input("Truck ID", value=a['truck_id'])
                submit_edit_job = st.form_submit_button("Update Assignment")
                if submit_edit_job:
                    tech = techs[tech_idx]
                    update = {
                        "badge_id": tech['badge_id'],
                        "technician_name": tech['name'],
                        "customer_name": customer_name,
                        "address": address,
                        "project_id": project_id,
                        "scheduled_time": scheduled_time.strftime("%H:%M"),
                        "truck_id": truck_id,
                        "service_date": selected_date_str,  # Use selected date here
                    }
                    update_assignment(edit_job_id, update)
                    st.success("Assignment updated!")
                    st.session_state.edit_job = False
                    st.rerun()
            st.button("Cancel Edit", on_click=lambda: st.session_state.update({'edit_job': False}))
        else:
            with st.form("assign_job"):
                tech_options = [f"{t['name']} ({t['badge_id']})" for t in techs]
                tech_idx = st.selectbox("Technician", options=range(len(tech_options)), format_func=lambda i: tech_options[i])
                customer_name = st.text_input("Customer Name")
                address = st.text_input("Address")
                project_id = st.text_input("Project ID")
                scheduled_time = st.time_input("Scheduled Time", datetime.time(9, 0))
                truck_id = st.text_input("Truck ID")
                submit_job = st.form_submit_button("Assign Job")
                if submit_job:
                    tech = techs[tech_idx]
                    now_ca = datetime.datetime.now(CA_TZ)
                    assignment = {
                        "badge_id": tech['badge_id'],
                        "technician_name": tech['name'],
                        "customer_name": customer_name,
                        "address": address,
                        "project_id": project_id,
                        "scheduled_time": scheduled_time.strftime("%H:%M"),
                        "truck_id": truck_id,
                        "verified": False,
                        "created_at": now_ca.isoformat(),
                        "service_date": selected_date_str,  # Use selected date here
                    }
                    add_assignment(assignment)
                    msg = f"""Bright Ideas Construction\n📅 Service: {selected_date_str} at {scheduled_time.strftime('%I:%M %p')}\n👷 Technician: {tech['name']}\n🔧 Project #: {project_id}\n🏠 Address: {address}\n🚚 Truck: {truck_id}\n✅ Verify: https://energybicverification.streamlit.app/?view=verify&badge_id={tech['badge_id']}\n"""
                    st.success("Assignment added!")
                    st.info("Auto Text Message:\n" + msg)
            st.session_state.edit_job = False

        st.subheader("Assignments for selected date")
        for a in list_assignments(for_date=selected_date_str):
            st.write(f"{a['scheduled_time']} | {a['technician_name']} | {a['customer_name']} | {a['address']} | {a['project_id']}")
            cols = st.columns(3)
            if cols[0].button(f"Edit job {a['_id']}"):
                st.session_state.edit_job = True
                st.session_state.edit_job_id = a['_id']
                st.rerun()
            if cols[1].button(f"Delete job {a['_id']}"):
                db.collection("assignments").document(a['_id']).delete()
                st.success(f"Deleted assignment {a['_id']}")
                st.rerun()
            sms_text = f"Bright Ideas Construction\nService: {selected_date_str} at {a['scheduled_time']}\nTechnician: {a['technician_name']}\nProject #: {a['project_id']}\nAddress: {a['address']}\nTruck: {a['truck_id']}\nVerify: https://energybicverification.streamlit.app/?view=verify&badge_id={a['badge_id']}\n"
            if cols[2].button(f"Copy SMS {a['_id']}"):
                st.code(sms_text, language='text')

        export_assignments_csv()

    # --- Bulk CSV Import Tab ---
    with tab3:
        csv_import_tab(db)

elif view == "verify":
    st.title("Customer: Verify Your Technician")
    badge_id = query_params.get("badge_id", [""])[0]
    if not badge_id:
        badge_id = st.text_input("Enter Technician Badge ID to verify jobs for selected date")
    if badge_id:
        selected_date = st.date_input("Select date (California time)", value=datetime.datetime.now(CA_TZ).date())
        selected_date_str = selected_date.strftime("%Y-%m-%d")
        jobs = list_assignments(for_date=selected_date_str, badge_id=badge_id)
        tech = next((t for t in list_technicians() if t['badge_id'] == badge_id), None)
        if tech:
            st.markdown(
                f"""
                <div style="display: flex; align-items: center; background: #f8f9fa; border-radius: 12px; padding: 18px; margin-bottom: 20px; box-shadow: 0 2px 6px rgba(0,0,0,0.07);">
                  <img src="{tech['photo_url']}" width="95" style="border-radius: 16px; margin-right: 24px; border: 2px solid #eee;">
                  <div>
                    <h3 style="margin-bottom: 5px;">Technician: {tech['name']}</h3>
                    <div style="color: #777;">Badge ID: <b>{badge_id}</b></div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        if not jobs:
            st.warning("No jobs found for this technician on the selected date.")
        else:
            st.markdown("### Your Scheduled Service")
            for idx, job in enumerate(jobs):
                with st.container():
                    st.markdown(
                        f"""
                        <div style="background: #e9f8ef; border-radius: 10px; padding: 18px 22px; margin-bottom: 18px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);">
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
                            st.rerun()
                    with colB:
                        with st.expander("Show full details"):
                            st.json(job)
            st.caption("If you have multiple scheduled jobs, verify each one separately.")
    st.caption("For best experience, view on mobile or desktop.")

else:
    st.error("Unknown view. Use ?view=admin or ?view=verify in the URL.")
