import boto3
import os
import json
import shutil
import argparse
import time
import datetime
import yaml
from typing import Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
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
write_lock = Lock()  # Lock for managing concurrent writes to the output file

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
    for prompt_name in ["full", "structured", "summary"]:
        response = retrieve_and_generate(bedrock_client, CONFIG['aws']['prompts'][prompt_name], document_uri)
        results[prompt_name] = response['output']['text']

    return results

def write_to_json_file(output_file: str, data: Dict[str, Any]):
    """
    Write the given data to the JSON output file, augmenting it incrementally.
    
    Args:
        output_file (str): Path to the JSON output file
        data (Dict[str, Any]): Data to write to the output file
    """
    with write_lock:  # Ensure that only one thread writes at a time
        if os.path.exists(output_file):
            # Load existing data and update
            with open(output_file, 'r') as file:
                existing_data = json.load(file)
        else:
            existing_data = {}

        existing_data.update(data)

        # Write updated data back to the file
        with open(output_file, 'w') as file:
            json.dump(existing_data, file, indent=4)

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

    # Prepare to iterate through all objects in the S3 bucket
    continuation_token = None  # Pagination handling
    pdf_file_keys = []

    while True:
        list_kwargs = {'Bucket': bucket_name, 'Prefix': prefix}
        if continuation_token:
            list_kwargs['ContinuationToken'] = continuation_token

        response = s3_client.list_objects_v2(**list_kwargs)

        for obj in response.get('Contents', []):
            pdf_file_key = obj['Key']
            if pdf_file_key.lower().endswith('.pdf'):  # Skip folders or non-PDF files
                pdf_file_keys.append(pdf_file_key)

        if not response.get('IsTruncated'):
            break
        continuation_token = response.get('NextContinuationToken')

    # Process invoices in parallel
    processed_count = 0
    with ThreadPoolExecutor() as executor:
        future_to_key = {
            executor.submit(process_invoice, s3_client, bedrock_client, bucket_name, pdf_file_key): pdf_file_key
            for pdf_file_key in pdf_file_keys
        }

        for future in as_completed(future_to_key):
            pdf_file_key = future_to_key[future]
            try:
                result = future.result()
                # Write result to the JSON output file as soon as it's available
                write_to_json_file(CONFIG['processing']['output_file'], {pdf_file_key: result})
                processed_count += 1
                print(f"Processed file: s3://{bucket_name}/{pdf_file_key}")
            except Exception as e:
                print(f"Failed to process s3://{bucket_name}/{pdf_file_key}: {str(e)}")

    return processed_count

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
