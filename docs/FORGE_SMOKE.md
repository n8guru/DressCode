# Forge text-to-pattern smoke test

DressCode runs in its dedicated `DressCode` conda environment on forge. From the
repository root, with the released checkpoints present at the paths in
`models/infer.yaml` and `nn/net_blocks.py`, run:

```bash
/home/n8/miniconda3/bin/conda run -n DressCode \
  python smoke_pattern.py "button-down shirt, oversized, long sleeve"
```

Success prints `SMOKE_TEST_PASSED` followed by the generated JSON specification,
SVG pattern, PNG preview, and caption paths. This intentionally uses `sim=False`;
Linux cloth simulation is a separate integration gate.

## License status

As checked on 2026-07-15, upstream commit `b623b60` contains no `LICENSE` file
and GitHub's repository license endpoint returns HTTP 404. Treat the source and
released weights as all-rights-reserved unless the authors publish explicit
terms; do not redistribute or use commercially without permission.
