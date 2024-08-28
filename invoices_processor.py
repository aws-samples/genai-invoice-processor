import boto3
import os
import json
import shutil
import argparse
import time
import datetime

# Input prompt for Bedrock knowledge base
input_prompt = """"extract data from attached  invoice in key value format."""

structured_input_prompt = """
Process the pdf invoice and list all metadata and values in json format. Then process the details in json and do following:
Format your analysis as a JSON object in following structure: \n
{
"Vendor": <"Amazon">,
"InvoiceDate":"<DD-MM-YYYY formatted invoice date>",
"StartDate":"<DD-MM-YYYY formatted service start date>",
"EndDate":"<DD-MM-YYYY formatted service end date>",
"CurrencyCode":"<Currency code based on the symbol and vendor details>",
"TotalAmountDue":"<100.90>"
"Description":"<Concise summary of the invoice description within 20 words>"
}
\n
Please proceed with the analysis based on the above instructions. Please don't state "Based on the .."
"""

# Input prompt for Bedrock knowledge base
summary_prompt = """Process the pdf invoice and summarize the invoice under 3 lines """

# Bedrock model ID
model_id = "anthropic.claude-3-sonnet-20240229-v1:0"

# Output file where results will be stored
output_file = "./" + "processed_invoice_output.json"

# Initialize boto3 session, s3 and bedrock client
session = boto3.session.Session(region_name='us-west-2') # TODO: make this region value a CONSTANT that user can change
region = session.region_name
s3 = boto3.client('s3')
bedrock_client = boto3.client(service_name='bedrock-agent-runtime', region_name=region)

# function to call bedrock kb retrieve_and_generate api which takes s3 url of the invoice and outputs the metadata stored inside it
def retrieveAndGenerate(input_prompt, sourceType, model_id, region, document_s3_uri=None):
    model_arn = f'arn:aws:bedrock:{region}::foundation-model/{model_id}'

    return bedrock_client.retrieve_and_generate(
        input={'text': input_prompt},
        retrieveAndGenerateConfiguration={
            'type': 'EXTERNAL_SOURCES',
            'externalSourcesConfiguration': {
                'modelArn': model_arn,
                'sources': [
                    {
                        "sourceType": sourceType,
                        "s3Location": {
                            "uri": document_s3_uri  
                        }
                    }
                ]
            }
        }
    )

# Function to batch process all invoices inside S3 bucket. It takes S3 bucket and folder name as input and processes all the invoices from it. 
# Returns a dictionary with key: file_name and value: metadata returned from the bedrock knowledge base

def batch_process_s3_bucket_invoices(bucket_name, local_download_folder):
# def batch_process_s3_bucket_invoices(bucket_name, prefix, local_download_folder):

    no_of_invoices_processed = 0 
    results = {}

    # Delete if the folder exists
    if os.path.exists(local_download_folder):
        # print(local_download_folder)
        shutil.rmtree(local_download_folder)
    # Create new folder for saving invoices
    os.makedirs(local_download_folder)  

    # Delete if output file exists
    if os.path.exists(output_file):
        os.remove(output_file)

    # Pagination handling
    continuation_token = None
    while True:
        if continuation_token:
            response = s3.list_objects_v2(Bucket=bucket_name, ContinuationToken=continuation_token)
            # response = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix, ContinuationToken=continuation_token)
        else:
            response = s3.list_objects_v2(Bucket=bucket_name)
            # response = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix)

        # Check if the folder contains any objects
        if 'Contents' in response:
            for obj in response['Contents']:
                
                pdf_file_key = obj['Key']
                document_uri = f"s3://{bucket_name}/{pdf_file_key}"

                try:
                    # Download the PDF from S3 and save it to the local folder
                    local_file_path = f"./{local_download_folder}/{pdf_file_key}"
                    with open(local_file_path, 'wb') as f: # TODO: QUESTION: why are we downloading the file?
                        s3.download_fileobj(bucket_name, pdf_file_key, f)

                    # Process pdf invoice stored in s3 bucket   
                    response = retrieveAndGenerate(input_prompt=input_prompt, sourceType="S3", model_id=model_id, region=region, document_s3_uri=document_uri)

                   # Process pdf invoice stored in s3 bucket   
                    limited_response = retrieveAndGenerate(input_prompt=structured_input_prompt, sourceType="S3", model_id=model_id, region=region, document_s3_uri=document_uri)

                    # Summarize pdf invoice stored in s3 bucket   
                    summary = retrieveAndGenerate(input_prompt=summary_prompt, sourceType="S3", model_id=model_id, region=region, document_s3_uri=document_uri)
                    
                    generated_text = response['output']['text']
                    limited_text = limited_response['output']['text']
                    summary_text = summary['output']['text']

                    print("Processed file: " + document_uri)
                    no_of_invoices_processed += 1
                    # merged_text = {**generated_text, **summary_text} # TODO: remove
                    results[pdf_file_key] = generated_text, limited_text, summary_text
                    # results[pdf_file_key]["metadata"] = generated_text, # TODO: remove
                    # results[pdf_file_key]["summary"] = summary_text # TODO: remove

                    # Write the generated text to the output file
                    with open(output_file, 'w') as file:
                        json.dump(results, file, indent=4)
                except Exception as e:
                    print(f"Failed to process {document_uri}:{str(e)}")

        # Check if there's more data to fetch
        if response.get('IsTruncated'):  # Means there are more files
            continuation_token = response['NextContinuationToken']
        else:
            break

    return no_of_invoices_processed 

def main():
    parser = argparse.ArgumentParser(description="Batch all pdf invoices inside a folder in a S3 bucket. Download the invoices locally along with json file containing information extracted from invoices.")
    parser.add_argument('--bucket_name', type=str, help="The name of the S3 bucket.")
    parser.add_argument('--prefix', type=str, help="S3 bucket folder (prefix) where invoices are stored.")
    
    args = parser.parse_args()
    
    start_time = time.time()
    
    no_of_invoices_processed = batch_process_s3_bucket_invoices(bucket_name=args.bucket_name, local_download_folder="invoice")    
    # no_of_invoices_processed = batch_process_s3_bucket_invoices(bucket_name=args.bucket_name, prefix=args.prefix, local_download_folder="invoice")    

    # End time
    end_time = time.time()

    # Calculate elapsed time in seconds
    elapsed_time = end_time - start_time

    # Convert elapsed time to hours, minutes, and seconds
    elapsed_time_formatted = str(datetime.timedelta(seconds=elapsed_time))

    print(f"Processed {no_of_invoices_processed} invoices in {elapsed_time_formatted}")
    print("To review invoices downloaded and corresponding data, run streamlit app using the command: python -m streamlit run review-invoice-data.py")

if __name__ == "__main__":
    main()