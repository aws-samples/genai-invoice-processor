import json

def generate_invoice_summary(invoice_data_file):
    with open(invoice_data_file, 'r') as file:
        invoice_data = json.load(file)

    total_amount = 0
    vendors = set()
    invoice_numbers = []

    for invoice in invoice_data.values():
        invoice_json = json.loads(invoice.split('{', 1)[1])
        
        total_amount += float(invoice_json['invoice_amount'].replace('$', ''))
        vendors.add(invoice_json['vendor_name'])
        invoice_numbers.append(invoice_json['invoice_number'])

    summary = {
        'total_invoices': len(invoice_data),
        'total_amount': f'${total_amount:.2f}',
        'unique_vendors': list(vendors),
        'invoice_numbers': invoice_numbers
    }

    return summary

if __name__ == '__main__':
    invoice_data_file = 'processed_invoice_output.json'
    summary = generate_invoice_summary(invoice_data_file)
    
    print("Invoice Summary:")
    print(f"Total Invoices: {summary['total_invoices']}")  
    print(f"Total Amount: {summary['total_amount']}")
    print(f"Unique Vendors: {', '.join(summary['unique_vendors'])}")
    print(f"Invoice Numbers: {', '.join(summary['invoice_numbers'])}")
