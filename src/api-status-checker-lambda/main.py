"""
ReviewLens AI: API - Status Checker Lambda (.zip)

This lightweight, high-speed function is invoked via API Gateway.
It retrieves the status of a specific job from DynamoDB.
"""

import os
import json
import boto3
from decimal import Decimal

# --- AWS Clients (Global Scope) ---
DYNAMODB_TABLE_NAME = os.environ['DYNAMODB_TABLE_NAME']
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
    Main Lambda handler triggered by API Gateway (GET /status/{job_id}).
    """
    print(f"Status-Checker handler started...")
    
    try:
        # 1. Get the job_id from the API Gateway path parameters
        job_id = event['pathParameters']['job_id']
        print(f"Checking status for job_id: {job_id}")
        
        # 2. Query the DynamoDB table
        response = table.get_item(
            Key={'job_id': job_id},
            ConsistentRead=True 
        )
        
        item = response.get('Item')
        
        # 3. If the job is not found, return a 404
        if not item:
            print(f"Job with id {job_id} not found.")
            return {
                'statusCode': 404,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': f'Job {job_id} not found'})
            }

        # 4. Calculate progress
        total = item.get('total_batches', 0)
        processed = item.get('processed_batches', 0)
        current_status = item.get('status', 'UNKNOWN')
        
        if total > 0:
            item['progress_percentage'] = round((processed / total) * 100, 2)
        else:
            item['progress_percentage'] = 0
            
        if processed >= total and current_status == 'IN_PROGRESS' and total > 0:
            item['status'] = 'PROCESSING_COMPLETE' 

        print(f"Job status found: {item.get('status')}")
        
        # 5. Return 200 OK
        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps(item, cls=DecimalEncoder)
        }
        
    except Exception as e:
        print(f"[ERROR] Error in Status-Checker Lambda: {e}")
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'An internal error occurred.'})
        }