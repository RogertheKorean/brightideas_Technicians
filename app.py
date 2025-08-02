import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, storage
import tempfile
import datetime

# --- Initialize Firebase with Streamlit secrets ---
if not firebase_admin._apps:
    firebase_creds = dict(st.secrets["firebase"])
    cred = credentials.Certificate(firebase_creds)
    firebase_admin.initialize_app(cred, {
        "storageBucket": "bright-ideas-verify-technician.firebasestorage.app"  # <-- Recommended bucket name (always .appspot.com)
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

# --- Streamlit App Layout ---
query_params = st.experimental_get_query_params()
view = query_params.get("view", ["admin"])[0]  # default to admin

if view == "admin":
    st.title("Bright Ideas Admin Panel (Firebase Version)")
    tab1, tab2 = st.tabs(["Technician Manager", "Assign Job"])

    with tab1:
        st.header("Add Technician with Photo Upload")
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

        st.subheader("All Technicians in Database")
        for d in list_technicians():
            st.write(f"👷 {d['name']} ({d['badge_id']})")
            st.image(d['photo_url'], width=120)
            # Edit/delete buttons (simple demo)
            cols = st.columns(2)
            if cols[0].button(f"Edit {d['badge_id']}"):
                st.info("(Edit not implemented in this demo, but can be added)")
            if cols[1].button(f"Delete {d['badge_id']}"):
                db.collection("technicians").document(d['badge_id']).delete()
                st.success(f"Deleted technician {d['badge_id']}")
                st.experimental_rerun()

    with tab2:
        st.header("Assign Job to Technician")
        techs = list_technicians()
        if not techs:
            st.info("Please add a technician first.")
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
                    assignment = {
                        "badge_id": tech['badge_id'],
                        "technician_name": tech['name'],
                        "customer_name": customer_name,
                        "address": address,
                        "project_id": project_id,
                        "scheduled_time": scheduled_time.strftime("%H:%M"),
                        "truck_id": truck_id,
                        "verified": False
                    }
                    add_assignment(assignment)
                    # Auto-generate SMS message
                    msg = f"""Bright Ideas Construction\n📅 Service: today at {scheduled_time.strftime('%I:%M %p')}\n👷 Technician: {tech['name']}\n🔧 Project #: {project_id}\n🏠 Address: {address}\n🚚 Truck: {truck_id}\n✅ Verify: https://energybicverification.streamlit.app/?view=verify&badge_id={tech['badge_id']}\n"""
                    st.success("Assignment added!")
                    st.info("Auto Text Message:\n" + msg)
            st.subheader("Today's Assignments")
            for a in list_assignments():
                st.write(f"{a['scheduled_time']} | {a['technician_name']} | {a['customer_name']} | {a['address']} | {a['project_id']}")
                # Edit/delete buttons
                cols = st.columns(2)
                if cols[0].button(f"Edit job {a['_id']}"):
                    st.info("(Edit not implemented in this demo, but can be added)")
                if cols[1].button(f"Delete job {a['_id']}"):
                    db.collection("assignments").document(a['_id']).delete()
                    st.success(f"Deleted assignment {a['_id']}")
                    st.experimental_rerun()

elif view == "verify":
    st.title("Customer: Verify Technician")
    badge_id = query_params.get("badge_id", [""])[0]
    if not badge_id:
        badge_id = st.text_input("Enter Technician Badge ID to verify jobs for today")
    if badge_id:
        jobs = list_assignments(badge_id=badge_id)
        if not jobs:
            st.warning("No jobs found for this technician today.")
        else:
            st.write("Select your job:")
            job_idx = st.radio(
                "Today's Assignments",
                options=range(len(jobs)),
                format_func=lambda i: f"{jobs[i]['scheduled_time']} | {jobs[i]['customer_name']} | {jobs[i]['address']} | {jobs[i]['project_id']}"
            )
            if st.button("I Verified"):
                verify_assignment(jobs[job_idx]['_id'])
                st.success("Thank you for verifying your technician!")
            st.write("Job details:")
            st.json(jobs[job_idx])
else:
    st.error("Unknown view. Use ?view=admin or ?view=verify in the URL.")
