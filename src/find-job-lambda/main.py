"""
ReviewLens AI: API - Find Job Lambda (.zip)

This lightweight, high-speed function is invoked via API Gateway.
It solves the "decoupling" problem between the frontend and backend.
"""

import os
import json
import boto3
from boto3.dynamodb.conditions import Key
from decimal import Decimal

# --- AWS Clients (Global Scope) ---
DYNAMODB_TABLE_NAME = os.environ['DYNAMODB_TABLE_NAME']
S3_BRONZE_BUCKET = os.environ['S3_BRONZE_BUCKET']
GSI_NAME = 'SourceFileIndex'
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(DYNAMODB_TABLE_NAME)

# --- CORS Headers ---
CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'GET,OPTIONS'
}

# --- Decimal Encoder ---
class DecimalEncoder(json.JSONEncoder):
    """
    Helper class to serialize DynamoDB's Decimal type into float
    for clean JSON responses.
    """
    def default(self, obj):
        if isinstance(obj, Decimal):
            if obj % 1 == 0:
                return int(obj)
            else:
                return float(obj)
        return super(DecimalEncoder, self).default(obj)

def handler(event: dict, context: object) -> dict:
    """
    Main Lambda handler triggered by API Gateway (GET /find-job/{upload_id}).
    """
    print(f"Find-job handler started...")
    try:
        # 1. Get 'upload_id' from the URL path parameter
        upload_id = event['pathParameters']['upload_id']
        
        # 2. Construct the S3 prefix
        source_file_prefix = f"s3://{S3_BRONZE_BUCKET}/uploads/{upload_id}/"
        print(f"Querying GSI '{GSI_NAME}' for: {source_file_prefix}")

        # 3. Query the GSI
        response = table.query(
            IndexName=GSI_NAME,
            KeyConditionExpression=Key('source_file').eq(source_file_prefix)
        )

        # 4. Return the job item if found
        if response.get('Items'):
            job_item = response['Items'][0]
            print(f"Job found. Returning job_id: {job_item.get('job_id')}")
            return {
                'statusCode': 200,
                'headers': CORS_HEADERS,
                # Usa il DecimalEncoder per serializzare la risposta
                'body': json.dumps(job_item, cls=DecimalEncoder) 
            }
        else:
            print("Job not yet found. The client should retry.")
            return {
                'statusCode': 404,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': 'Job not yet registered. Please try again.'})
            }

    except Exception as e:
        print(f"[ERROR] An error occurred in find-job: {e}")
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Internal server error.'})
        }