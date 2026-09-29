set -e
cd ~/cloth_test/task-134122
mkdir -p fit/f9
PY=/home/n8/cloth_test/task-133870/gcenv/bin/python
for k in pants:bellbottom_jeans shirt:collar_shirt_70s; do $PY scripts/garment_textures.py --obj inputs/rt8/${k#*:}_sim.obj --kind ${k%%:*} --lift-m 0.054874 --out tex9 2>&1 | grep TEXTURES; done
blender -b fit/f8/dressable_g9_outfit.blend --python scripts/apply_materials.py -- --tex tex9 --master inputs/amy_a08_v3_master.blend --out fit/f9/outfit_mat.blend 2>&1 | grep -c MATERIALS_OK
cp fit/f9/outfit_mat.blend out/dressable_g9_outfit_70s_134122.blend
sha256sum out/dressable_g9_outfit_70s_134122.blend
cp fit/f9/outfit_mat.blend fit/f9/outfit_mat_hair.blend
blender -b fit/f9/outfit_mat_hair.blend --python scripts/hair_over_outfit.py -- --object "Dressable Shirt" --object "Dressable Pants" --report fit/f9/hair_over_outfit.json 2>&1 | grep -E "HAIR_CLEAR" || true
blender -b out/dressable_g9_outfit_70s_134122.blend --python scripts/verify_outfit_gates.py -- --out out/verify_gates.json > out/verify_gates.log 2>&1
grep VERIFY_DONE out/verify_gates.log
blender -b fit/f9/outfit_mat_hair.blend --python scripts/render_dressed.py -- --out render/final_f9 --cpu --samples 128 > render/final_f9.log 2>&1
grep RENDER_DONE render/final_f9.log
scp -q out/dressable_g9_outfit_70s_134122.blend mac:character-foundry-wt/task-134122-inputs/
echo SHIPPED
