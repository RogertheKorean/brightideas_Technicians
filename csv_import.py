import streamlit as st
import datetime

def csv_import_tab(db):
    st.header("\U0001F4E5 Bulk Import Technicians & Assignments (CSV)")
    st.write("""
    **Instructions:**  
    - CSV must have columns: `Technician Name`, `Badge ID`, `Photo URL` (optional), `Project ID`, `Customer Name`, `Address`, `Scheduled Time`, `Truck ID`
    - If a technician already exists by badge ID, info will be updated if changed.
    - Assignments will always be added.
    """)
    csv_file = st.file_uploader("Upload CSV file", type=["csv"])

    if csv_file:
        import pandas as pd
        try:
            df = pd.read_csv(csv_file)
            st.subheader("Preview")
            st.dataframe(df.head(10))

            # Validate columns
            required_cols = ["Technician Name", "Badge ID", "Project ID", "Customer Name", "Address", "Scheduled Time", "Truck ID"]
            missing = [col for col in required_cols if col not in df.columns]
            if missing:
                st.error(f"Missing columns: {missing}")
            else:
                # Show errors/warnings for missing badge id or time format
                errors = []
                for idx, row in df.iterrows():
                    if not str(row["Badge ID"]).strip():
                        errors.append(f"Row {idx+2}: Missing Badge ID")
                    try:
                        # Accepts both HH:MM or YYYY-MM-DD HH:MM
                        datetime.time.fromisoformat(str(row["Scheduled Time"])) if len(str(row["Scheduled Time"])) <= 5 else datetime.datetime.fromisoformat(str(row["Scheduled Time"]))
                    except Exception:
                        errors.append(f"Row {idx+2}: Invalid time '{row['Scheduled Time']}'")
                if errors:
                    st.error("CSV validation errors found:")
                    st.write("\n".join(errors))
                else:
                    if st.button("Bulk Import Now"):
                        added_techs, updated_techs, assignments_added = 0, 0, 0
                        for _, row in df.iterrows():
                            # Add/update technician
                            tech_ref = db.collection("technicians").document(str(row["Badge ID"]))
                            tech_data = {
                                "name": row["Technician Name"],
                                "badge_id": row["Badge ID"],
                            }
                            # Optional photo
                            if "Photo URL" in df.columns and pd.notnull(row["Photo URL"]):
                                tech_data["photo_url"] = row["Photo URL"]
                            prev = tech_ref.get()
                            if prev.exists:
                                prev_data = prev.to_dict()
                                if prev_data["name"] != tech_data["name"] or (tech_data.get("photo_url") and prev_data.get("photo_url") != tech_data.get("photo_url")):
                                    tech_ref.update(tech_data)
                                    updated_techs += 1
                            else:
                                tech_ref.set(tech_data)
                                added_techs += 1

                            # Add assignment
                            # Accept both "HH:MM" or full datetime
                            sched = str(row["Scheduled Time"])
                            if len(sched) <= 5:
                                now = datetime.datetime.now()
                                sched_dt = f"{now.date()} {sched}"
                            else:
                                sched_dt = sched
                            assignment = {
                                "badge_id": row["Badge ID"],
                                "technician_name": row["Technician Name"],
                                "customer_name": row["Customer Name"],
                                "address": row["Address"],
                                "project_id": row["Project ID"],
                                "scheduled_time": sched,
                                "created_at": datetime.datetime.now().isoformat(),
                                "truck_id": row["Truck ID"],
                                "verified": False,
                            }
                            db.collection("assignments").add(assignment)
                            assignments_added += 1
                        st.success(f"Import finished: {added_techs} new techs, {updated_techs} updated, {assignments_added} assignments added.")

        except Exception as e:
            st.error(f"Error reading CSV: {e}")

    with st.expander("\U0001F4CB CSV Template Example"):
        st.write("""
| Technician Name | Badge ID | Photo URL | Project ID | Customer Name | Address | Scheduled Time | Truck ID |
|-----------------|----------|-----------|------------|--------------|---------|---------------|----------|
| John Smith      | T001     | https://...jpg | P1001 | Kim Lee  | 123 Main St | 09:00 | TK101   |
| Jane Doe        | T002     | https://...jpg | P1002 | Sam Park | 456 Oak Rd  | 10:30 | TK102   |
        """)
        st.markdown("**Save as .csv before uploading. 'Photo URL' is optional.**")
