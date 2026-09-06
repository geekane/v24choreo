import urllib.request, ssl, re, json

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

token = 'chp_eyJrZXkiOiJsYmZldmFmOGdrejNkdTF1ZmpkNjN0cW5xZ3llaDFtenl1Y3BqZGI2a2w5dThxbnpzdnBqIn0=iqpGqw'

req = urllib.request.Request('https://console.choreo.dev/', headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
        html = resp.read().decode('utf-8', errors='ignore')
        scripts = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html)
        print('All scripts:', scripts)
        link_scripts = re.findall(r'href=["\']([^"\']+\.js)["\']', html)
        print('Link scripts:', link_scripts)

        for js in js_files:
            js_url = 'https://console.choreo.dev' + js
            r2 = urllib.request.Request(js_url, headers={'User-Agent': 'Mozilla/5.0'})
            try:
                with urllib.request.urlopen(r2, context=ctx, timeout=8) as resp2:
                    content = resp2.read().decode('utf-8', errors='ignore')
                    # Look for queryAPIUrl or runtime-logs or component-logs
                    for kw in ['query-api', 'runtimelogs', 'component_logs', 'insights', 'download-logs', 'apim-devportal']:
                        if kw in content:
                            print(f'Found {kw} in {js}')
                            # extract surrounding snippet
                            idx = content.find(kw)
                            snippet = content[max(0, idx-100):min(len(content), idx+150)]
                            print(f'Snippet: {snippet}')
            except Exception as e:
                pass
except Exception as e:
    print('Err:', e)
