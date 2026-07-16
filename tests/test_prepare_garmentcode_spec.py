import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/task-2906-sewinggpt-shirt.json"
SCRIPT = ROOT / "scripts/prepare_garmentcode_spec.py"


class PrepareGarmentCodeSpecTest(unittest.TestCase):
    def test_only_offsets_panel_y(self):
        source = json.loads(FIXTURE.read_text())
        expected = copy.deepcopy(source)
        for panel in expected["pattern"]["panels"].values():
            panel["translation"][1] += 84.0

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "prepared_specification.json"
            subprocess.run(
                [sys.executable, str(SCRIPT), str(FIXTURE), str(output)],
                check=True,
            )
            self.assertEqual(json.loads(output.read_text()), expected)


if __name__ == "__main__":
    unittest.main()
