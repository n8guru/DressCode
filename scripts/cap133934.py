import sys, hashlib, json
from playwright.sync_api import sync_playwright
out = sys.argv[1]
urls = {"s15_70s_ic_dressed": "http://127.0.0.1:5133/ic_dressed_amy.html?glb=amy_dressable_g9_s15_70s.glb",
        "s15_70s_live_alive": "http://127.0.0.1:5133/live_alive.html?glb=amy_dressable_g9_s15_70s.glb"}
res = {}
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=__import__("glob").glob("/home/n8/.cache/ms-playwright/chromium-1234/chrome-linux*/chrome")[0], args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
    for tag, u in urls.items():
        pg = b.new_page(viewport={"width": 900, "height": 1100})
        errs = []
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(u); pg.wait_for_timeout(25000)
        f = f"{out}/{tag}.png"; pg.screenshot(path=f)
        res[tag] = {"url": u.replace("127.0.0.1", "forge.tail2b8e3e.ts.net"), "png": f,
                    "sha256": hashlib.sha256(open(f, "rb").read()).hexdigest(), "console_errors": errs[:8]}
        pg.close()
    b.close()
print("CAPTURE " + json.dumps(res))
