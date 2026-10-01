cd ~/cloth_test/task-135614/browser
PORT=8937
(python3 -m http.server $PORT --bind 127.0.0.1 > http.log 2>&1 &) ; sleep 1
FL="--headless=new --no-sandbox --use-angle=swiftshader --enable-unsafe-swiftshader --ignore-gpu-blocklist --window-size=900,1100 --hide-scrollbars --virtual-time-budget=240000 --run-all-compositor-stages-before-draw"
for v in "front:0:2.05" "back:180:2.05" "back34:145:1.25" "front34:-30:1.25"; do
  n=${v%%:*}; r=${v#*:}; yaw=${r%%:*}; d=${r#*:}
  timeout 300 google-chrome $FL --screenshot=$PWD/t135614_browser_$n.png "http://127.0.0.1:$PORT/gate.html?yaw=$yaw&d=$d" > chrome_$n.log 2>&1
  echo "SHOT $n $(sha256sum t135614_browser_$n.png | cut -c1-64)"
done
timeout 300 google-chrome $FL --dump-dom "http://127.0.0.1:$PORT/gate.html" > gate_dom.html 2> chrome_dom.log
grep -o 'BROWSER_GATE[^<]*' gate_dom.html | head -c 1500 > t135614_browser_gate.txt
cat t135614_browser_gate.txt | head -c 1500; echo
pkill -f "http.server $PORT"
