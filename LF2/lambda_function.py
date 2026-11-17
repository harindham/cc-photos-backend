import json, os, re
import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection

lex = boto3.client('lexv2-runtime')
es = OpenSearch(
    hosts=[{'host': os.environ['ES_HOST'], 'port': 443}],
    http_auth=(os.environ['ES_USER'], os.environ['ES_PASS']),
    use_ssl=True, verify_certs=True,
    connection_class=RequestsHttpConnection
)

STOP = {'show','me','photos','photo','pictures','with','in','them','of','and','the','find','a','an'}
CORS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': '*',
    'Access-Control-Allow-Methods': 'GET,OPTIONS'
}

def get_keywords(q):
    keywords = []
    try:
        resp = lex.recognize_text(
            botId=os.environ['BOT_ID'],
            botAliasId=os.environ['BOT_ALIAS_ID'],
            localeId='en_US',
            sessionId='search-session',
            text=q
        )
        slots = resp.get('sessionState', {}).get('intent', {}).get('slots', {}) or {}
        for s in slots.values():
            if s and s.get('value'):
                v = s['value'].get('interpretedValue') or s['value'].get('originalValue')
                if v: keywords.append(v.lower())
    except Exception as e:
        print('Lex error', e)
    # fallback if Lex returned nothing
    if not keywords:
        keywords = [w for w in re.findall(r'[a-z0-9]+', q.lower()) if w not in STOP]
    return keywords

def singular(w):
    return w[:-1] if w.endswith('s') and len(w) > 3 else w

def lambda_handler(event, context):
    q = (event.get('queryStringParameters') or {}).get('q', '').strip()
    if not q:
        return {'statusCode': 200, 'headers': CORS, 'body': json.dumps({'results': []})}

    keywords = get_keywords(q)
    if not keywords:
        return {'statusCode': 200, 'headers': CORS, 'body': json.dumps({'results': []})}

    # match any keyword (also its singular form: "dogs" -> "dog")
    terms = list({t for k in keywords for t in (k, singular(k))}) # comment added
    query = {'query': {'terms': {'labels': terms}}, 'size': 50}
    res = es.search(index='photos', body=query)

    results = []
    for hit in res['hits']['hits']:
        d = hit['_source']
        results.append({
            'url': f"https://{d['bucket']}.s3.amazonaws.com/{d['objectKey']}", #comment
            'labels': d['labels']
        })
    return {'statusCode': 200, 'headers': CORS, 'body': json.dumps({'results': results})}