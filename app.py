import streamlit as st
import datetime

# In-memory storage
if 'technicians' not in st.session_state:
    st.session_state.technicians = []
if 'assignments' not in st.session_state:
    st.session_state.assignments = []
if 'verifications' not in st.session_state:
    st.session_state.verifications = []

# --- Detect View from Query Parameter ---
query_params = st.experimental_get_query_params()
view = query_params.get("view", ["admin"])[0]  # default to 'admin' if not set

if view == "admin":
    st.title("Bright Ideas Admin Panel")

    tab1, tab2 = st.tabs(["Technician Manager", "Assign Job"])

    with tab1:
        st.header("Add Technician")
        with st.form("add_tech"):
            tech_name = st.text_input("Technician Name")
            badge_id = st.text_input("Badge ID")
            photo_filename = st.text_input("Photo filename (upload soon)")
            submitted = st.form_submit_button("Add Technician")
            if submitted:
                st.session_state.technicians.append({
                    "name": tech_name,
                    "badge_id": badge_id,
                    "photo": photo_filename
                })
                st.success(f"Technician {tech_name} added.")

        st.subheader("All Technicians")
        st.table(st.session_state.technicians)

    with tab2:
        st.header("Assign Job to Technician")
        if len(st.session_state.technicians) == 0:
            st.info("Please add a technician first.")
        else:
            with st.form("assign_job"):
                tech_options = [f"{t['name']} ({t['badge_id']})" for t in st.session_state.technicians]
                tech_idx = st.selectbox("Technician", options=range(len(tech_options)), format_func=lambda i: tech_options[i])
                customer_name = st.text_input("Customer Name")
                address = st.text_input("Address")
                project_id = st.text_input("Project ID")
                scheduled_time = st.time_input("Scheduled Time", datetime.time(9, 0))
                truck_id = st.text_input("Truck ID")
                submit_job = st.form_submit_button("Assign Job")
                if submit_job:
                    tech = st.session_state.technicians[tech_idx]
                    st.session_state.assignments.append({
                        "badge_id": tech['badge_id'],
                        "technician_name": tech['name'],
                        "customer_name": customer_name,
                        "address": address,
                        "project_id": project_id,
                        "scheduled_time": scheduled_time.strftime("%H:%M"),
                        "truck_id": truck_id,
                        "verified": False
                    })
                    msg = f"""Bright Ideas Construction\n📅 Service: today at {scheduled_time.strftime("%I:%M %p")}
👷 Technician: {tech['name']}
🔧 Project #: {project_id}
🏠 Address: {address}
🚚 Truck: {truck_id}
✅ Verify: http://localhost:8501/?view=verify&badge_id={tech['badge_id']}
"""
                    st.success("Assignment added.")
                    st.info("Auto Text Message:\n" + msg)
            st.subheader("Today's Assignments")
            st.table(st.session_state.assignments)

elif view == "verify":
    st.title("Customer: Verify Technician")
    badge_id = query_params.get("badge_id", [""])[0]
    if not badge_id:
        badge_id = st.text_input("Enter Technician Badge ID to verify jobs for today")
    if badge_id:
        jobs = [a for a in st.session_state.assignments if a['badge_id'] == badge_id]
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
                jobs[job_idx]['verified'] = True
                st.session_state.verifications.append({
                    "badge_id": badge_id,
                    "job_idx": job_idx,
                    "timestamp": datetime.datetime.now().isoformat()
                })
                st.success("Thank you for verifying your technician!")
            st.write("Job details:")
            st.json(jobs[job_idx])

else:
    st.error("Unknown view. Use ?view=admin or ?view=verify in the URL.")

st.sidebar.info("Switch views by using ?view=admin or ?view=verify in the URL. For customer, use ?view=verify&badge_id=XXX for a direct verification link.")

