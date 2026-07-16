#!/usr/bin/env python3
"""Generate a deterministic DressCode PBR texture triplet and evidence JSON."""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
from PIL import Image

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "nn"))

from material_gen.test_finetune import gen_texture  # noqa: E402


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def image_metrics(path):
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)
    edge_mae = float(
        (
            np.abs(rgb[:, 0] - rgb[:, -1]).mean()
            + np.abs(rgb[0] - rgb[-1]).mean()
        )
        / (2.0 * 255.0)
    )
    return {
        "width": int(rgb.shape[1]),
        "height": int(rgb.shape[0]),
        "mean_rgb": [round(float(v), 3) for v in rgb.mean(axis=(0, 1))],
        "std_rgb": [round(float(v), 3) for v in rgb.std(axis=(0, 1))],
        "edge_mae_normalized": round(edge_mae, 6),
        "sha256": sha256(path),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--prompt",
        default=(
            "white linen fabric, fine natural woven fibers, subtle slub texture, "
            "matte, seamless tile"
        ),
    )
    parser.add_argument("--seed", type=int, default=2928)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/task-2928-pbr")
    parser.add_argument("--model-dir", type=Path, default=ROOT / "nn/material_gen")
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    generator = gen_texture(str(args.model_dir))
    generator.run(args.prompt, str(args.output), seed=args.seed)

    files = {}
    for kind in ("diffuse", "normal", "roughness"):
        path = args.output / f"texture_{kind}.png"
        if not path.is_file():
            raise RuntimeError(f"missing generated map: {path}")
        files[kind] = image_metrics(path)

    valid = all(
        metrics["width"] == 512
        and metrics["height"] == 512
        and max(metrics["std_rgb"]) > 2.0
        for metrics in files.values()
    ) and len({metrics["sha256"] for metrics in files.values()}) == 3

    evidence = {
        "task_id": 2928,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prompt": args.prompt,
        "seed": args.seed,
        "model_dir": str(args.model_dir),
        "torch": torch.__version__,
        "gpu": torch.cuda.get_device_name(0),
        "result": "SMOKE_TEST_PASSED" if valid else "SMOKE_TEST_FAILED",
        "artifact_root": os.path.relpath(args.output, ROOT),
        "maps": files,
    }
    evidence_path = args.evidence or args.output / "evidence.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))
    if not valid:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
