import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import plotly.express as px
from io import BytesIO
import base64

st.set_page_config(page_title="📑 Invoice CRM Dashboard", layout="wide")

st.sidebar.title("🔐 Upload Google Auth JSON")
json_file = st.sidebar.file_uploader("Upload service_account.json", type="json")

GOOGLE_SHEET_ID = "11ryUchUIGvsnW6cVsuI1rXYAk06xP3dZWcbQ8vyLFN4"
VISIBLE_COLUMNS = [
    "Customer name", "Customer email", "Product", "Product Description",
    "Price", "Invoice Link", "Status", "Date Created"
]

if json_file:
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(
            eval(json_file.read()), scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        )
        client = gspread.authorize(creds)
        sheet = client.open_by_key(GOOGLE_SHEET_ID).sheet1
        data = sheet.get_all_records()
        df = pd.DataFrame(data)

        df.columns = df.columns.str.strip()
        missing = [col for col in VISIBLE_COLUMNS if col not in df.columns]
        if missing:
            st.error(f"❌ Missing columns: {missing}")
            st.stop()

        df = df[VISIBLE_COLUMNS]
        df["Date Created"] = pd.to_datetime(df["Date Created"], errors='coerce')
        df["Invoice Age (Days)"] = (datetime.today() - df["Date Created"]).dt.days

        st.title("📊 Invoice CRM Dashboard")

        # Filters
        with st.expander("🔍 Filters", expanded=False):
            status_filter = st.multiselect("Filter by Status", df["Status"].unique(), default=list(df["Status"].unique()))
            product_filter = st.multiselect("Filter by Product", df["Product"].unique(), default=list(df["Product"].unique()))
            search_text = st.text_input("Search Customer name/email").lower()

        filtered_df = df[df["Status"].isin(status_filter) & df["Product"].isin(product_filter)]
        if search_text:
            filtered_df = filtered_df[
                filtered_df["Customer name"].str.lower().str.contains(search_text) |
                filtered_df["Customer email"].str.lower().str.contains(search_text)
            ]

        # Metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Invoices", len(filtered_df))
        col2.metric("Total Revenue", f"${filtered_df['Price'].sum():,.2f}")
        col3.metric("Avg Invoice Age", f"{filtered_df['Invoice Age (Days)'].mean():.1f} days")
        col4.metric("Unpaid Invoices", len(filtered_df[filtered_df["Status"] != "Paid"]))

        # Invoice Age Groups
        overdue_30 = filtered_df[filtered_df["Invoice Age (Days)"] > 30]
        overdue_21 = filtered_df[(filtered_df["Invoice Age (Days)"] > 21) & (filtered_df["Invoice Age (Days)"] <= 30)]
        overdue_7 = filtered_df[(filtered_df["Invoice Age (Days)"] > 7) & (filtered_df["Invoice Age (Days)"] <= 21)]

        with st.expander("📅 Invoice Aging Notifications", expanded=False):
            st.warning(f"Over 30 days: {len(overdue_30)}")
            st.info(f"21–30 days: {len(overdue_21)}")
            st.info(f"7–21 days: {len(overdue_7)}")

        # Charts
        if not filtered_df.empty:
            monthly_sales = filtered_df.copy()
            monthly_sales["Month"] = monthly_sales["Date Created"].dt.to_period("M").astype(str)
            sales_summary = monthly_sales.groupby("Month")["Price"].sum().reset_index()
            st.subheader("📈 Monthly Sales")
            st.plotly_chart(px.bar(sales_summary, x="Month", y="Price", title="Revenue by Month"), use_container_width=True)

        # Table
        st.subheader("📄 Invoice Table")
        st.dataframe(filtered_df, use_container_width=True)

        # Download CSV
        csv = filtered_df.to_csv(index=False).encode('utf-8')
        st.download_button("⬇️ Download CSV", csv, "invoices.csv", "text/csv")

        # PDF Export (Optional Demo)
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas

        def create_pdf(df):
            buffer = BytesIO()
            c = canvas.Canvas(buffer, pagesize=letter)
            c.setFont("Helvetica", 10)
            c.drawString(30, 750, "Invoice Summary Export")
            y = 730
            for _, row in df.iterrows():
                text = f"{row['Customer name']} - {row['Product']} - ${row['Price']} - {row['Status']}"
                c.drawString(30, y, text)
                y -= 15
                if y < 50:
                    c.showPage()
                    y = 750
            c.save()
            pdf_bytes = buffer.getvalue()
            return pdf_bytes

        pdf_file = create_pdf(filtered_df)
        st.download_button("⬇️ Export PDF", pdf_file, "invoices.pdf", "application/pdf")

        # Add/Edit New Invoice
        with st.expander("➕ Add New Invoice"):
            with st.form("new_invoice"):
                new_name = st.text_input("Customer Name")
                new_email = st.text_input("Customer Email")
                new_product = st.text_input("Product")
                new_desc = st.text_area("Product Description")
                new_price = st.number_input("Price", min_value=0.0)
                new_link = st.text_input("Invoice Link")
                new_status = st.selectbox("Status", ["Pending", "Paid", "Overdue"])
                new_date = st.date_input("Date Created", datetime.today())
                submitted = st.form_submit_button("Append to Sheet")
                if submitted:
                    sheet.append_row([
                        new_name, new_email, new_product, new_desc,
                        new_price, new_link, new_status, str(new_date)
                    ])
                    st.success("✅ New invoice added!")

        # Send/Resend (Demo Only — replace with real SMTP or SendGrid logic)
        with st.expander("✉️ Send or Resend Email"):
            for i, row in filtered_df.iterrows():
                if st.button(f"Send to {row['Customer email']}", key=f"send_{i}"):
                    st.success(f"📬 Email sent to {row['Customer email']} (simulate)")

    except Exception as e:
        st.error(f"❌ Failed to load data: {e}")
else:
    st.info("⬅️ Upload your Google JSON file to start.")
