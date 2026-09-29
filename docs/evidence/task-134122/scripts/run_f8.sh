set -e
cd ~/cloth_test/task-134122
read _ J S < inputs/rt5.inputs
blender -b inputs/amy_a08_v3_master.blend --python scripts/retarget_tighten.py -- --gp-blend /home/n8/cloth_test/task-133870/g9/amy_gp_v3_master.blend --lift-m 0.054874 --out-dir inputs/rt8 --jeans-ease-mm 3.5 --jeans-keep 0.12 --jeans-relax-iters 6 --fill-iters 30 --flare-iters 14 --shirt-ease-mm 7 --shirt-keep 0.2 --over-jeans-ease-mm 17 --garment pants:$J --garment shirt:$S 2>&1 | grep -E "FILL|GUARD|RETARGET |Error|Traceback" | cut -c1-400
blender -b inputs/amy_a08_v3_master.blend --python scripts/fit_native_g9_outfit.py -- --garment pants:inputs/rt8/bellbottom_jeans_sim.obj --garment shirt:inputs/rt8/collar_shirt_70s_sim.obj --lift-m 0.054874 --clearance-mm 5 --out-dir fit/f8 > fit/f8.log 2>&1
grep OUTFIT_FIT_DONE fit/f8.log
PY=/home/n8/cloth_test/task-133870/gcenv/bin/python
for k in pants:bellbottom_jeans shirt:collar_shirt_70s; do $PY scripts/garment_textures.py --obj inputs/rt8/${k#*:}_sim.obj --kind ${k%%:*} --lift-m 0.054874 --out tex8 2>&1 | grep TEXTURES; done
blender -b fit/f8/dressable_g9_outfit.blend --python scripts/apply_materials.py -- --tex tex8 --master inputs/amy_a08_v3_master.blend --out fit/f8/outfit_mat.blend 2>&1 | grep -c MATERIALS_OK
cp fit/f8/outfit_mat.blend out/dressable_g9_outfit_70s_134122.blend
sha256sum out/dressable_g9_outfit_70s_134122.blend
cp fit/f8/outfit_mat.blend fit/f8/outfit_mat_hair.blend
blender -b fit/f8/outfit_mat_hair.blend --python scripts/hair_over_outfit.py -- --object "Dressable Shirt" --object "Dressable Pants" --report fit/f8/hair_over_outfit.json 2>&1 | grep -E "HAIR_CLEAR|Error|Traceback" || true
blender -b out/dressable_g9_outfit_70s_134122.blend --python scripts/verify_outfit_gates.py -- --out out/verify_gates.json > out/verify_gates.log 2>&1
grep VERIFY_DONE out/verify_gates.log
blender -b fit/f8/outfit_mat_hair.blend --python scripts/hair_diag.py 2>&1 | grep HAIRDIAG
blender -b fit/f8/outfit_mat_hair.blend --python scripts/render_dressed.py -- --out render/final_f8 --cpu --samples 128 > render/final_f8.log 2>&1
grep RENDER_DONE render/final_f8.log
