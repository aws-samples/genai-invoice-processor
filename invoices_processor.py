import boto3
import os
import json
import shutil
import argparse
import time
import datetime
import yaml
from typing import Dict, Any, Tuple
from mypy_boto3_bedrock_runtime.client import BedrockRuntimeClient
from mypy_boto3_s3.client import S3Client


# Load configuration from YAML file
def load_config():
    """
    Load and return the configuration from the 'config.yaml' file.
    """
    with open('config.yaml', 'r') as file:
        return yaml.safe_load(file)

CONFIG = load_config()

# Prompts for different types of invoice analysis
# These prompts are used to instruct the AI model on how to process the invoices
FULL_INPUT_PROMPT = "Extract data from attached invoice in key-value format."

STRUCTURED_INPUT_PROMPT = """
Process the pdf invoice and list all metadata and values in json format. Then process the details in json and do following:
Format your analysis as a JSON object in following structure:
{
"Vendor": "<Amazon>",
"InvoiceDate":"<DD-MM-YYYY formatted invoice date>",
"StartDate":"<DD-MM-YYYY formatted service start date>",
"EndDate":"<DD-MM-YYYY formatted service end date>",
"CurrencyCode":"<Currency code based on the symbol and vendor details>",
"TotalAmountDue":"<100.90>"
"Description":"<Concise summary of the invoice description within 20 words>"
}
Please proceed with the analysis based on the above instructions. Please don't state "Based on the .."
"""

SUMMARY_PROMPT = "Process the pdf invoice and summarize the invoice under 3 lines"

def initialize_aws_clients() -> Tuple[S3Client, BedrockRuntimeClient]:
    """
    Initialize and return AWS S3 and Bedrock clients.
    
    Returns:
        Tuple[S3Client, BedrockRuntimeClient]
    """
    return (
        boto3.client('s3', region_name=CONFIG['aws']['region_name']),
        boto3.client(service_name='bedrock-agent-runtime', 
                     region_name=CONFIG['aws']['region_name'])
    )

def retrieve_and_generate(bedrock_client: BedrockRuntimeClient, input_prompt: str, document_s3_uri: str) -> Dict[str, Any]:
    """
    Use AWS Bedrock to retrieve and generate invoice data based on the provided prompt and S3 document URI.
    
    Args:
        bedrock_client (BedrockRuntimeClient): AWS Bedrock client
        input_prompt (str): Prompt for the AI model
        document_s3_uri (str): S3 URI of the invoice document
    
    Returns:
        Dict[str, Any]: Generated data from Bedrock
    """
    model_arn = f'arn:aws:bedrock:{CONFIG["aws"]["region_name"]}::foundation-model/{CONFIG["aws"]["model_id"]}'
    return bedrock_client.retrieve_and_generate(
        input={'text': input_prompt},
        retrieveAndGenerateConfiguration={
            'type': 'EXTERNAL_SOURCES',
            'externalSourcesConfiguration': {
                'modelArn': model_arn,
                'sources': [
                    {
                        "sourceType": "S3",
                        "s3Location": {"uri": document_s3_uri}
                    }
                ]
            }
        }
    )

def process_invoice(s3_client: S3Client, bedrock_client: BedrockRuntimeClient, bucket_name: str, pdf_file_key: str) -> Dict[str, str]:
    """
    Process a single invoice by downloading it from S3 and using Bedrock to analyze it.
    
    Args:
        s3_client (S3Client): AWS S3 client
        bedrock_client (BedrockRuntimeClient): AWS Bedrock client
        bucket_name (str): Name of the S3 bucket
        pdf_file_key (str): S3 key of the PDF invoice
    
    Returns:
        Dict[str, Any]: Processed invoice data
    """
    document_uri = f"s3://{bucket_name}/{pdf_file_key}"
    local_file_path = os.path.join(CONFIG['processing']['local_download_folder'], pdf_file_key)

    # Ensure the local directory exists and download the invoice from S3
    os.makedirs(os.path.dirname(local_file_path), exist_ok=True)
    s3_client.download_file(bucket_name, pdf_file_key, local_file_path)

    # Process invoice with different prompts
    results = {}
    for prompt_name, prompt in [
        ("full", FULL_INPUT_PROMPT),
        ("structured", STRUCTURED_INPUT_PROMPT),
        ("summary", SUMMARY_PROMPT)
    ]:
        response = retrieve_and_generate(bedrock_client, prompt, document_uri)
        results[prompt_name] = response['output']['text']

    return results

def batch_process_s3_bucket_invoices(s3_client: S3Client, bedrock_client: BedrockRuntimeClient, bucket_name: str, prefix: str = "") -> int:
    """
    Batch process all invoices in an S3 bucket or a specific prefix within the bucket.
    
    Args:
        s3_client (S3Client): AWS S3 client
        bedrock_client (BedrockRuntimeClient): AWS Bedrock client
        bucket_name (str): Name of the S3 bucket
        prefix (str, optional): S3 prefix to filter invoices. Defaults to "".
    
    Returns:
        int: Number of processed invoices
    """
    # Clear and recreate local download folder
    shutil.rmtree(CONFIG['processing']['local_download_folder'], ignore_errors=True)
    os.makedirs(CONFIG['processing']['local_download_folder'], exist_ok=True)

    processed_invoices = 0
    results = {}

    # Iterate through all objects in S3 bucket
    continuation_token = None # Pagination handling
    while True:
        list_kwargs = {'Bucket': bucket_name, 'Prefix': prefix}
        if continuation_token:
            list_kwargs['ContinuationToken'] = continuation_token

        response = s3_client.list_objects_v2(**list_kwargs)

        for obj in response.get('Contents', []):
            pdf_file_key = obj['Key']
            try:
                results[pdf_file_key] = process_invoice(s3_client, bedrock_client, bucket_name, pdf_file_key)
                processed_invoices += 1
                print(f"Processed file: s3://{bucket_name}/{pdf_file_key}")
            except Exception as e:
                print(f"Failed to process s3://{bucket_name}/{pdf_file_key}: {str(e)}")

        if not response.get('IsTruncated'):
            break
        continuation_token = response.get('NextContinuationToken')

    # Save results to output file
    with open(CONFIG['processing']['output_file'], 'w') as file:
        json.dump(results, file, indent=4)

    return processed_invoices

def main():
    """
    Main function to run the invoice processing script.
    Parses command-line arguments, initializes AWS clients, and processes invoices.
    """
    parser = argparse.ArgumentParser(description="Batch process PDF invoices from an S3 bucket.")
    parser.add_argument('--bucket_name', required=True, type=str, help="The name of the S3 bucket.")
    parser.add_argument('--prefix', type=str, default="", help="S3 bucket folder (prefix) where invoices are stored.")
    args = parser.parse_args()

    s3_client, bedrock_client = initialize_aws_clients()

    start_time = time.time()
    processed_invoices = batch_process_s3_bucket_invoices(s3_client, bedrock_client, args.bucket_name, args.prefix)
    elapsed_time = time.time() - start_time
    elapsed_time_formatted = str(datetime.timedelta(seconds=elapsed_time))

    print(f"Processed {processed_invoices} invoices in {elapsed_time_formatted}")
    print("To review invoices downloaded and corresponding data, run streamlit app using the command: python -m streamlit run review-invoice-data.py")

if __name__ == "__main__":
    main()