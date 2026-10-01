set -e
cd ~/cloth_test/task-135614
F=${F:-f11}; T=${T:-tex11}
PY=/home/n8/cloth_test/task-133870/gcenv/bin/python
for k in pants:bellbottom_jeans shirt:collar_shirt_70s; do $PY scripts/garment_textures.py --obj inputs/${RT:-rt9}/${k#*:}_sim.obj --kind ${k%%:*} --lift-m 0.054874 --out $T 2>&1 | grep TEXTURES; done
blender -b fit/$F/dressable_g9_outfit.blend --python scripts/apply_materials.py -- --tex $T --master inputs/amy_a08_v3_master.blend --out fit/$F/outfit_mat.blend 2>&1 | grep -c MATERIALS_OK
cp fit/$F/outfit_mat.blend fit/$F/outfit_mat_hair.blend
blender -b fit/$F/outfit_mat_hair.blend --python scripts/hair_over_outfit.py -- --object "Dressable Shirt" --object "Dressable Pants" --behind-shoulders --report fit/$F/hair_over_outfit.json 2>&1 | grep -E "HAIR_" | cut -c1-300
