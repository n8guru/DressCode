# runs ON n8razer: headless browser + CDP, poll window.__gate until the 120-frame gate finishes
import json, subprocess, time, urllib.request, websocket, os
os.chdir('/tmp/gate142131')
srv = subprocess.Popen(['python3', '-m', 'http.server', '8942', '--bind', '127.0.0.1'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
br = subprocess.Popen(['/usr/bin/google-chrome', '--headless=new', '--no-sandbox', '--use-angle=swiftshader', '--enable-unsafe-swiftshader',
    '--ignore-gpu-blocklist', '--window-size=900,1100', '--remote-debugging-port=9342', '--remote-allow-origins=*', '--user-data-dir=/tmp/gate142131/prof2',
    'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        try:
            tabs = json.load(urllib.request.urlopen('http://127.0.0.1:9342/json')); break
        except Exception: time.sleep(0.5)
    ws = websocket.create_connection([t for t in tabs if t['type'] == 'page'][0]['webSocketDebuggerUrl'], timeout=60)
    n = [0]
    def call(m, p=None):
        n[0] += 1; ws.send(json.dumps({'id': n[0], 'method': m, 'params': p or {}}))
        while True:
            r = json.loads(ws.recv())
            if r.get('id') == n[0]: return r
    call('Page.navigate', {'url': 'http://127.0.0.1:8942/gate.html'})
    t0 = time.time(); res = None
    while time.time() - t0 < 900:
        r = call('Runtime.evaluate', {'expression': 'JSON.stringify({g: window.__gate || null, t: document.getElementById("gate").textContent})', 'returnByValue': True})
        v = json.loads(r['result']['result']['value'])
        if v['g'] is not None: res = v; break
        time.sleep(2)
    out = {'elapsed_s': round(time.time() - t0, 1), 'gate': res}
    open('t142131_browser_gate.json', 'w').write(json.dumps(out, indent=1))
    print((res or {}).get('t', 'TIMEOUT')[:3000])
finally:
    br.kill(); srv.kill()
