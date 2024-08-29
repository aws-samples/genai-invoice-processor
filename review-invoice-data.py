import json
import streamlit as st
import os
from streamlit_pdf_reader import pdf_reader
import yaml
from typing import List, Dict

def load_config():
    """
    Load and return the configuration from the 'config.yaml' file.
    """
    with open('config.yaml', 'r') as file:
        return yaml.safe_load(file)

CONFIG = load_config()

def load_invoice_data(file_path: str) -> Dict[str, Dict[str, str]]:
    """
    Load processed invoice data from a JSON file.
    
    Args:
        file_path (str): Path to the JSON file containing processed invoice data.
    
    Returns:
        dict: Processed invoice data
    """
    with open(file_path, 'r') as file:
        return json.load(file)

def get_invoice_files(folder: str) -> List[str]:
    """
    Get a sorted list of PDF invoice files in the specified folder.
    
    Args:
        folder (str): Path to the folder containing invoice PDFs.
    
    Returns:
        list: Sorted list of PDF filenames
    """
    return sorted([f for f in os.listdir(folder) if f.endswith('.pdf')])

def display_invoice_data(invoice_data_catalog: Dict[str, Dict[str, str]], invoice_filename: str) -> None:
    """
    Display the processed data for a specific invoice in the Streamlit app.
    
    Args:
        invoice_data_catalog (dict): Catalog of all processed invoice data
        invoice_filename (str): Filename of the current invoice
    """
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

def main() -> None:
    """
    Main function to run the Streamlit app for reviewing processed invoice data.
    """
    st.set_page_config(layout="wide")
    
    # Load processed invoice data and get list of invoice files
    invoice_data = load_invoice_data(CONFIG['processing']['output_file'])
    invoice_files = [key for key in invoice_data.keys()]
    # checking that for each invoice with data in the output file, it has the actual invoice stored in the local download folder
    assert all([os.path.exists(os.path.join(os.getcwd(), CONFIG['processing']['local_download_folder'], file)) for file in invoice_files])
    
    # Initialize or use existing counter for navigation
    if 'counter' not in st.session_state:
        st.session_state.counter = 0
    
    st.header("Review Invoice and Extracted Data")
    
    # Navigation buttons
    col1, col2 = st.columns(2)
    with col1:
        if st.button("⬅️ Previous") and st.session_state.counter > 0:
            st.session_state.counter -= 1
    with col2:
        if st.button("Next ➡️") and st.session_state.counter < len(invoice_files) - 1:
            st.session_state.counter += 1
    
    # Get current invoice filename and path
    invoice_filename = invoice_files[st.session_state.counter]
    invoice_file_path = os.path.join(CONFIG['processing']['local_download_folder'], invoice_filename)
    
    # Display invoice PDF and extracted data side by side
    invoice, data = st.columns([3, 2])
    
    with invoice:
        st.header("Invoice")
        pdf_reader(invoice_file_path, key=f"pdf_reader_{invoice_filename}")
    
    with data:
        st.header("Generated Data")
        display_invoice_data(invoice_data, invoice_filename)

if __name__ == "__main__":
    main()