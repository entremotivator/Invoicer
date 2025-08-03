import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.oauth2 import service_account
import json
import yagmail
from datetime import datetime
from fpdf import FPDF
import os

# Constants
GSHEET_URL = "https://docs.google.com/spreadsheets/d/11ryUchUIGvsnW6cVsuI1rXYAk06xP3dZWcbQ8vyLFN4"
VISIBLE_COLUMNS = ["Customer name", "Customer email", "Product", "Product Description", "Price", "Invoice Link", "Status", "Date Created"]
SENDER_EMAIL = "entremotivator@gmail.com"

st.set_page_config(page_title="Invoice CRM Dashboard", layout="wide")
st.title("📄 Multi-Client Invoice CRM Dashboard")

# Sidebar for credentials
st.sidebar.title("🔐 Google Auth")
json_file = st.sidebar.file_uploader("Upload Google JSON Credentials", type="json")

if json_file:
    creds = service_account.Credentials.from_service_account_info(
        json.loads(json_file.read()),
        scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_url(GSHEET_URL)
    sheet_names = [ws.title for ws in sh.worksheets()]
    
    selected_tab = st.selectbox("📁 Choose Client Sheet", sheet_names)
    worksheet = sh.worksheet(selected_tab)
    df = pd.DataFrame(worksheet.get_all_records())

    # Ensure columns
    if "Date Created" not in df.columns:
        df["Date Created"] = datetime.today().strftime('%Y-%m-%d')
    df = df[VISIBLE_COLUMNS]
    df["Date Created"] = pd.to_datetime(df["Date Created"], errors='coerce')
    df["Invoice Age (Days)"] = (datetime.today() - df["Date Created"]).dt.days

    # 🔍 Search + Filter Section
    st.subheader("🔍 Search & Filter Options")
    with st.expander("🔧 Advanced Filters"):
        col1, col2, col3 = st.columns(3)

        # Text search
        search_query = col1.text_input("Search Customer Name or Email").lower()
        # Status filter
        status_filter = col2.multiselect("Filter by Status", options=df["Status"].unique(), default=list(df["Status"].unique()))
        # Product filter
        product_filter = col3.multiselect("Filter by Product", options=df["Product"].unique(), default=list(df["Product"].unique()))

        # Date range
        date_min = df["Date Created"].min()
        date_max = df["Date Created"].max()
        date_range = st.date_input("📆 Filter by Date Created Range", value=(date_min, date_max))

        # Filter logic
        filtered_df = df[
            df["Status"].isin(status_filter) &
            df["Product"].isin(product_filter) &
            df["Date Created"].between(pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1]))
        ]
        if search_query:
            filtered_df = filtered_df[
                filtered_df["Customer name"].str.lower().str.contains(search_query) |
                filtered_df["Customer email"].str.lower().str.contains(search_query)
            ]

    st.markdown(f"**Filtered Results: {len(filtered_df)} invoices shown**")

    # --- Metrics Section ---
    st.subheader("📊 Invoice Metrics")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Invoices", len(filtered_df))
    col2.metric("Total Paid", f"${filtered_df[filtered_df['Status'] == 'Paid']['Price'].sum():,.2f}")
    col3.metric("Pending Amount", f"${filtered_df[filtered_df['Status'] == 'Pending']['Price'].sum():,.2f}")
    col4.metric("Overdue", f"${filtered_df[filtered_df['Status'] == 'Overdue']['Price'].sum():,.2f}")

    # Monthly Chart
    chart_df = filtered_df.copy()
    chart_df["Month"] = chart_df["Date Created"].dt.to_period("M").astype(str)
    monthly_sales = chart_df.groupby("Month")["Price"].sum().reset_index()
    if not monthly_sales.empty:
        st.subheader("📈 Monthly Revenue")
        st.bar_chart(monthly_sales.set_index("Month"))

    # Aging Summary
    st.subheader("📆 Invoice Aging Buckets")
    age_7 = filtered_df[filtered_df["Invoice Age (Days)"] <= 7]
    age_21 = filtered_df[(filtered_df["Invoice Age (Days)"] > 7) & (filtered_df["Invoice Age (Days)"] <= 21)]
    age_30 = filtered_df[(filtered_df["Invoice Age (Days)"] > 21) & (filtered_df["Invoice Age (Days)"] <= 30)]
    age_overdue = filtered_df[filtered_df["Invoice Age (Days)"] > 30]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("0–7 Days", len(age_7))
    c2.metric("8–21 Days", len(age_21))
    c3.metric("22–30 Days", len(age_30))
    c4.metric("30+ Days", len(age_overdue))

    # Notifications
    with st.expander("🔔 Notifications for 30+ Days Overdue"):
        for _, row in age_overdue.iterrows():
            st.warning(f"{row['Customer name']} - {row['Product']} - {row['Invoice Age (Days)']} days old")

    # Editable Table
    st.subheader("📋 Live Invoice Table (Filtered)")
    filtered_display = st.data_editor(filtered_df.drop(columns=["Invoice Age (Days)"]), num_rows="dynamic", use_container_width=True)

    if st.button("💾 Save Changes to Sheet"):
        worksheet.clear()
        worksheet.append_row(filtered_display.columns.tolist())
        for _, row in filtered_display.iterrows():
            worksheet.append_row(row.tolist())
        st.success("✅ Sheet updated!")

    # Add Invoice
    st.subheader("➕ Add New Invoice")
    with st.form("add_invoice_form"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Customer Name")
        email = c2.text_input("Customer Email")
        product = c1.text_input("Product")
        description = c2.text_input("Product Description")
        price = c2.number_input("Price", step=1.0)
        link = c1.text_input("Invoice Link")
        status = c2.selectbox("Status", ["Pending", "Paid", "Overdue"])
        submitted = st.form_submit_button("Add Invoice")
        if submitted:
            date_created = datetime.today().strftime('%Y-%m-%d')
            new_row = [name, email, product, description, price, link, status, date_created]
            worksheet.append_row(new_row)
            st.success("✅ Invoice added!")

    # Email sending
    st.subheader("📧 Email Invoice")
    email_password = st.text_input("Gmail App Password for entremotivator@gmail.com", type="password")

    if email_password:
        yag = yagmail.SMTP(SENDER_EMAIL, email_password)
        for i, row in filtered_df.iterrows():
            if st.button(f"📤 Send Email to {row['Customer name']}", key=f"send_{i}"):
                email_body = f"""Hi {row['Customer name']},

Here is your invoice for {row['Product']}:

Description: {row['Product Description']}
Amount: ${row['Price']}
Status: {row['Status']}
Link: {row['Invoice Link']}
Date Created: {row['Date Created'].strftime('%Y-%m-%d')}

Thank you,
EntreMotivator
"""
                yag.send(to=row["Customer email"], subject=f"Invoice for {row['Product']}", contents=email_body)
                st.success(f"✅ Email sent to {row['Customer email']}")

    # PDF Export
    st.subheader("📄 Export Invoice to PDF")
    for i, row in filtered_df.iterrows():
        if st.button(f"🧾 Export PDF: {row['Customer name']}", key=f"pdf_{i}"):
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=12)
            pdf.cell(200, 10, txt="Invoice", ln=True, align="C")
            for col in VISIBLE_COLUMNS:
                val = row[col] if not pd.isna(row[col]) else ""
                pdf.cell(200, 10, txt=f"{col}: {val}", ln=True)
            path = f"/tmp/invoice_{row['Customer name'].replace(' ', '_')}.pdf"
            pdf.output(path)
            with open(path, "rb") as f:
                st.download_button(
                    f"⬇️ Download PDF for {row['Customer name']}",
                    data=f,
                    file_name=os.path.basename(path),
                    mime="application/pdf"
                )

    # CSV Export
    st.subheader("⬇️ Export CSV")
    csv_data = filtered_df.to_csv(index=False).encode("utf-8")
    st.download_button("📥 Download Filtered CSV", data=csv_data, file_name=f"{selected_tab}_filtered_invoices.csv", mime="text/csv")

else:
    st.warning("Please upload a valid Google service JSON file.")
