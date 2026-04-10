import base64
import json
import subprocess
import time
import uuid

def send_push(secret, msg):
    url = "https://push.connie.hk/push"
    ts = str(int(time.time()))
    nonce = str(uuid.uuid4())
    
    # Match shell version exactly: compact JSON without extra spaces
    body_json = json.dumps({"msg": msg}, ensure_ascii=False, separators=(',', ':'))
    
    # Signature: HMAC-SHA256(TS . NONCE . BODY, SECRET)
    payload = f"{ts}.{nonce}.{body_json}"
    proc = subprocess.run(
        [
            'openssl', 'dgst', '-sha256', '-hmac', secret, '-binary'
        ],
        input=payload.encode('utf-8'),
        capture_output=True,
        check=True,
    )
    sig_base64 = base64.b64encode(proc.stdout).decode('utf-8').replace('\n', '')

    try:
        curl = subprocess.run(
            [
                'curl', '-s', '-o', '/tmp/plane-history-push.out', '-w', '%{http_code}',
                url,
                '-H', 'Content-Type: application/json',
                '-H', f'X-Timestamp: {ts}',
                '-H', f'X-Nonce: {nonce}',
                '-H', f'X-Signature: {sig_base64}',
                '-d', body_json,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return int(curl.stdout.strip())
    except Exception as e:
        print(f"Push notification failed: {e}", flush=True)
        return None
