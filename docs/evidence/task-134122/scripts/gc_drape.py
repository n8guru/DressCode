import argparse, json
from pathlib import Path
from pygarment.meshgen.boxmeshgen import BoxMesh
from pygarment.meshgen.simulation import run_sim
import pygarment.data_config as data_config
from pygarment.meshgen.sim_config import PathCofig
ap = argparse.ArgumentParser()
ap.add_argument('--pattern_spec', required=True)
ap.add_argument('--sim_config', default='./assets/Sim_props/default_sim_props.yaml')
ap.add_argument('--body_name', default='f_smpl_average_A40')
ap.add_argument('--smpl_body', action='store_true')
ap.add_argument('--body_seg', default=None)
a = ap.parse_args()
props = data_config.Properties(a.sim_config)
props.set_section_stats('sim', fails={}, sim_time={}, spf={}, fin_frame={}, body_collisions={}, self_collisions={})
props.set_section_stats('render', render_time={})
spec = Path(a.pattern_spec)
name, _, _ = spec.stem.rpartition('_')
sysp = data_config.Properties('/home/n8/cloth_test/task-134122/gc/system.json')
paths = PathCofig(in_element_path=spec.parent, out_path=sysp['output'], in_name=name,
                  body_name=a.body_name, smpl_body=a.smpl_body, add_timestamp=True)
if a.body_seg: paths.body_seg = Path(a.body_seg).resolve()
bm = BoxMesh(paths.in_g_spec, props['sim']['config']['resolution_scale'])
bm.load()
bm.serialize(paths, store_panels=False, uv_config=props['render']['config']['uv_texture'])
props.serialize(paths.element_sim_props)
run_sim(bm.name, props, paths, save_v_norms=False, store_usd=False, optimize_storage=False, verbose=False)
props.serialize(paths.element_sim_props)
print("DRAPE_OUT", paths.out_el)
print("STATS", json.dumps({k: props['sim']['stats'][k] for k in props['sim']['stats']}, default=str))
