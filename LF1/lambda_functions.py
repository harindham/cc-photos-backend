import json, os, urllib.parse
from datetime import datetime
import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection

s3 = boto3.client('s3') #comment added
rekognition = boto3.client('rekognition')

es = OpenSearch(
    hosts=[{'host': os.environ['ES_HOST'], 'port': 443}],
    http_auth=(os.environ['ES_USER'], os.environ['ES_PASS']),
    use_ssl=True, verify_certs=True,
    connection_class=RequestsHttpConnection
)

def lambda_handler(event, context):
    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        key = urllib.parse.unquote_plus(record['s3']['object']['key'])

        # 1. Rekognition labels
        rek = rekognition.detect_labels(
            Image={'S3Object': {'Bucket': bucket, 'Name': key}},
            MaxLabels=20, MinConfidence=80
        )
        labels = [l['Name'].lower() for l in rek['Labels']]

        # 2. Custom labels from metadata
        head = s3.head_object(Bucket=bucket, Key=key)
        meta = head.get('Metadata', {})            # keys come back lowercase, prefix stripped
        custom = meta.get('customlabels', '')
        if custom:
            labels += [c.strip().lower() for c in custom.split(',') if c.strip()]

        labels = list(dict.fromkeys(labels))       # de-dupe, keep order

        # 3. Index document
        doc = {
            'objectKey': key,
            'bucket': bucket,
            'createdTimestamp': head['LastModified'].strftime('%Y-%m-%dT%H:%M:%S'),
            'labels': labels
        }
        es.index(index='photos', id=key, body=doc)
        print('Indexed', doc)
    return {'statusCode': 200}