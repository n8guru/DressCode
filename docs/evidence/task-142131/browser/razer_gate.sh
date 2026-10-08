# runs ON n8razer (forge never hosts the browser): headless three.js gate for task 142131
cd /tmp/gate142131
(python3 -m http.server 8941 --bind 127.0.0.1 > http.log 2>&1 &); sleep 2
CR=/usr/bin/google-chrome
FL="--headless=new --no-sandbox --use-angle=swiftshader --enable-unsafe-swiftshader --ignore-gpu-blocklist --window-size=900,1100 --hide-scrollbars --virtual-time-budget=600000 --run-all-compositor-stages-before-draw --user-data-dir=/tmp/gate142131/prof"
for v in front:0:2.05 back:180:2.05 back34:145:1.25 front34:-30:1.25; do
  n=${v%%:*}; r=${v#*:}; yaw=${r%%:*}; d=${r#*:}
  timeout 400 $CR $FL --screenshot=$PWD/t142131_browser_$n.png "http://127.0.0.1:8941/gate.html?yaw=$yaw&d=$d" > shot_$n.log 2>&1
  echo SHOT $n $(sha256sum t142131_browser_$n.png | cut -c1-64)
done
timeout 600 $CR $FL --dump-dom "http://127.0.0.1:8941/gate.html" > gate_dom.html 2> dom.log
python3 -c "import re;s=open('gate_dom.html').read();m=re.search(r'<pre id=.gate.>([^<]*)',s);print(m.group(1)[:2500])" | tee t142131_browser_gate.txt
pkill -f "http.server 8941"
