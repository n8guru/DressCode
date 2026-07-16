#!/usr/bin/env python3
"""Generate one SewingGPT pattern from a text prompt without cloth simulation."""

import argparse
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
sys.path[:0] = [
    str(REPO_ROOT / "packages"),
    str(REPO_ROOT / "nn"),
    str(REPO_ROOT / "nn" / "evaluation_scripts"),
]

from predict_class import infer  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run DressCode text-to-sewing-pattern inference on one prompt."
    )
    parser.add_argument("prompt", help="Garment description for SewingGPT")
    parser.add_argument(
        "--config", default="./models/infer.yaml", help="Inference YAML path"
    )
    parser.add_argument("--temperature", type=float, default=0.7)
    args = parser.parse_args()

    os.chdir(REPO_ROOT)
    generator = infer(args.config)
    specification = Path(
        generator.forward(args.prompt, temperature=args.temperature, sim=False)
    ).resolve()

    required = [
        specification,
        specification.with_name("pred_0_pattern.svg"),
        specification.with_name("pred_0_pattern.png"),
        specification.parent.parent / "caption.txt",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        parser.error(f"inference returned without required artifacts: {missing}")

    print("SMOKE_TEST_PASSED")
    for artifact in required:
        print(f"ARTIFACT {artifact} {artifact.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
