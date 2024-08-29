import json
import streamlit as st
import os
from streamlit_pdf_reader import pdf_reader
import yaml

def load_config():
    with open('config.yaml', 'r') as file:
        return yaml.safe_load(file)

CONFIG = load_config()

def load_invoice_data(file_path):
    with open(file_path, 'r') as file:
        return json.load(file)

def get_invoice_files(folder):
    return sorted([f for f in os.listdir(folder) if f.endswith('.pdf')])

def display_invoice_data(invoice_data_catalog, invoice_filename):
    try:
        invoice_data = invoice_data_catalog[invoice_filename]
        
        st.subheader("Summary")
        st.write(invoice_data["summary"]) # TODO: this renders the summary as markdown and there are characters in the text which render the text as italics, etc
                                            # need to fix this

        st.subheader("Structured Data")
        st.json(json.loads(invoice_data["structured"]))
        
        st.subheader("Detailed Text")
        st.text(invoice_data["full"])
    except KeyError:
        st.error(f"Data for {invoice_filename} not found.")
    except Exception as e:
        st.error(f"Error displaying data: {str(e)}")

def main():
    st.set_page_config(layout="wide")
    
    invoice_data = load_invoice_data(CONFIG['processing']['output_file'])
    invoice_files = get_invoice_files(CONFIG['processing']['local_download_folder'])
    
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
    invoice_file_path = os.path.join(CONFIG['processing']['local_download_folder'], invoice_filename)
    
    invoice, data = st.columns([3, 2])
    
    with invoice:
        st.header("Invoice")
        pdf_reader(invoice_file_path, key=f"pdf_reader_{invoice_filename}")
    
    with data:
        st.header("Generated Data")
        display_invoice_data(invoice_data, invoice_filename)

if __name__ == "__main__":
    main()