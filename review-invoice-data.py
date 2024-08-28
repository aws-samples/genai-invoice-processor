import json
import streamlit as st
import os
from streamlit_pdf_reader import pdf_reader

def load_invoice_data(file_path):
    with open(file_path, 'r') as file:
        return json.load(file)

def get_invoice_files(folder):
    return sorted([f for f in os.listdir(folder) if f.endswith('.pdf')])

def display_invoice_data(invoice_data, invoice_filename):
    try:
        detailed_text, json_string, summary_text = invoice_data[invoice_filename]
        
        st.subheader("Summary")
        st.write(summary_text)
        
        st.subheader("Structured Data")
        st.json(json.loads(json_string))
        
        st.subheader("Detailed Text")
        st.text(detailed_text)
    except KeyError:
        st.error(f"Data for {invoice_filename} not found.")
    except Exception as e:
        st.error(f"Error displaying data: {str(e)}")

def main():
    st.set_page_config(layout="wide")
    
    local_download_folder = "invoice"
    invoice_data_file = "processed_invoice_output.json"
    
    invoice_data = load_invoice_data(invoice_data_file)
    invoice_files = get_invoice_files(local_download_folder)
    
    if 'counter' not in st.session_state:
        st.session_state.counter = 0
    
    st.header("Review Invoice and Extracted Data")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("⬅️ Previous") and st.session_state.counter > 0:
            st.session_state.counter -= 1
    with col2:
        if st.button("Next ➡️") and st.session_state.counter < len(invoice_files) - 1:
            st.session_state.counter += 1
    
    invoice_filename = invoice_files[st.session_state.counter]
    invoice_file_path = os.path.join(local_download_folder, invoice_filename)
    
    invoice, data = st.columns([3, 2])
    
    with invoice:
        st.header("Invoice")
        pdf_reader(invoice_file_path, key=f"pdf_reader_{invoice_filename}")
    
    with data:
        st.header("Generated Data")
        display_invoice_data(invoice_data, invoice_filename)

if __name__ == "__main__":
    main()