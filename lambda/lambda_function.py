import boto3
import urllib.parse
import logging
import os

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client('s3')
sns = boto3.client('sns')

CLEAN_BUCKET = 'healthworks-lambda-manage-productionencounterbucke-yoqwb36evr2x'
INFECTED_BUCKET = 'dev-sftp-infected-quarantine'
SNS_TOPIC_ARN = 'arn:aws:sns:us-east-1:744640651507:dev-SFTP-Malware-Detected-Alert' 

def get_unique_key(bucket, key):
    """
    Checks if a file exists in the target bucket. 
    If it does, appends a numeric suffix (e.g., _1, _2) until a unique key is found.
    """
    base_name, extension = os.path.splitext(key)
    final_key = key
    counter = 1
    
    while True:
        try:
            # Check if the object exists
            s3.head_object(Bucket=bucket, Key=final_key)
            # If no error is thrown, the file exists; increment counter
            final_key = f"{base_name}_{counter}{extension}"
            counter += 1
        except:
            # If head_object fails (usually 404), the key is available
            break
    return final_key

def lambda_handler(event, context):
    logger.info(f"EVENT: {event}")
    try:
        detail = event.get('detail', {})
        
        # Support for both real GuardDuty events and manual Console tests
        s3_info = detail.get('s3ObjectDetails') or detail.get('resourceDetails', {}).get('s3BucketDetails')
        
        if not s3_info:
            logger.error("No S3 details found in event. Check EventBridge Pattern or Test JSON.")
            return {"status": "ERROR", "message": "Key mismatch in JSON"}

        source_bucket = s3_info['bucketName']
        original_key = urllib.parse.unquote_plus(s3_info['objectKey'])
        scan_result = detail.get('scanResultDetails', {}).get('scanResultStatus')

        # --- BRANCH 1: NO THREATS FOUND ---
        if scan_result == "NO_THREATS_FOUND":
            logger.info(f"Processing clean file: {original_key}")
            
            # Get unique destination key for Clean Bucket
            final_key = get_unique_key(CLEAN_BUCKET, original_key)

            s3.copy_object(
                Bucket=CLEAN_BUCKET, 
                CopySource={'Bucket': source_bucket, 'Key': original_key}, 
                Key=final_key,
                TaggingDirective='REPLACE'
            )
            s3.delete_object(Bucket=source_bucket, Key=original_key)
            
            logger.info(f"SUCCESS: Moved {original_key} to Production as {final_key}")
            return {"status": "SUCCESS", "destination": final_key}
            
        # --- BRANCH 2: THREATS FOUND ---
        elif scan_result == "THREATS_FOUND":
            logger.warning(f"MALWARE DETECTED in: {original_key}")

            # Get unique destination key for Infected Bucket
            final_key = get_unique_key(INFECTED_BUCKET, original_key)

            s3.copy_object(
                Bucket=INFECTED_BUCKET, 
                CopySource={'Bucket': source_bucket, 'Key': original_key}, 
                Key=final_key, 
                TaggingDirective='REPLACE'
            )
            s3.delete_object(Bucket=source_bucket, Key=original_key)
            
            sns.publish(
                TopicArn=SNS_TOPIC_ARN, 
                Subject="MALWARE ALERT", 
                Message=f"Infected file detected and quarantined.\nOriginal Name: {original_key}\nStored as: {final_key}"
            )
            
            logger.info(f"QUARANTINED: {original_key} moved as {final_key}")
            return {"status": "QUARANTINED", "destination": final_key}

    except Exception as e:
        logger.error(f"CRITICAL ERROR: {str(e)}")
        raise e