import json
import streamlit as st
import os
from streamlit_pdf_reader import pdf_reader

st.set_page_config(layout="wide")

local_download_folder = "invoice"
invoice_data_file = "processed_invoice_output.json"

# Load invoice data from the JSON file
with open(invoice_data_file, 'r') as file:
    invoice_data = json.load(file)

if 'counter' not in st.session_state:
    st.session_state.counter = 0

# Get list of invoice files in the folder
invoice_files = [f for f in os.listdir(local_download_folder) if f.endswith('.pdf')]
invoice_files.sort()  # Sort the files to ensure consistent navigation

def next_invoice():
    if st.session_state.counter < len(invoice_files) - 1:
        st.session_state.counter += 1
    display_invoice()

def prev_invoice():
    if st.session_state.counter > 0:
        st.session_state.counter -= 1
    display_invoice()

def display_invoice():
    # Get the current invoice filename and path
    invoice_filename = invoice_files[st.session_state.counter]
    invoice_file_path = os.path.join(local_download_folder, invoice_filename)

    # Ensure the key format matches exactly with the JSON keys
    invoice_key = os.path.join(local_download_folder, invoice_filename)  # Include folder path if needed

    # Display the PDF invoice
    with invoice:
        st.header("Invoice")
        pdf_reader(invoice_file_path, key=f"pdf_reader_{invoice_filename}")

    # Display the generated data
    with data:
        st.header("Generated Data")
        try:
            # Extracting the three parts from the JSON data
            detailed_text, json_string, summary_text = invoice_data[invoice_key]

            st.subheader("Summary")
            st.write(summary_text)
            
            st.subheader("Structured Data")
            st.json(json.loads(json_string))  # Parse the JSON string and display it as JSON

            st.subheader("Detailed Text")
            st.text(detailed_text)  # Display the detailed text as plain text

        except KeyError:
            st.error(f"Data for {invoice_filename} not found.")
        except Exception as e:
            st.error(f"Error displaying data: {str(e)}")

st.header("Review Invoice and Extracted Data")
st.write("Click Next to start")

# Create columns for navigation buttons at the top
button_cols = st.columns(2)
with button_cols[0]:
    st.button("⬅️ Previous", on_click=prev_invoice)
with button_cols[1]:
    st.button("Next ➡️", on_click=next_invoice)

# Adjust the column width. First column width is fixed at 3 relative units, the second at 2 relative units.
invoice, data = st.columns([3, 2])

# Display the first invoice and its data initially
display_invoice()
