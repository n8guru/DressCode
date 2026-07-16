#!/usr/bin/env python3
"""Translate a SewingGPT specification into GarmentCode's body-height frame.

The JSON schemas are already compatible. SewingGPT emits panels around y=10--20
cm, while GarmentCode's included A-pose bodies use a floor-origin frame with the
torso around y=95--110 cm. This adapter preserves panel geometry, rotations,
stitches, and metadata and applies only the explicit vertical offset.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--y-offset-cm", type=float, default=84.0)
    args = parser.parse_args()

    specification = json.loads(args.input.read_text())
    panels = specification["pattern"]["panels"]
    for panel in panels.values():
        panel["translation"][1] += args.y_offset_cm

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(specification, indent=2) + "\n")


if __name__ == "__main__":
    main()
