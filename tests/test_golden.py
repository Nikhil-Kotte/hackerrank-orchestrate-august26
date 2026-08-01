from pathlib import Path

from router.cli import main

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden" / "output_rules_only.csv"


def test_no_model_reproduces_the_frozen_rules_output(tmp_path):
    out = tmp_path / "output.csv"
    main(["--dataset", "dataset", "--output", str(out), "--also-write", "", "--no-model"])

    assert out.read_bytes() == GOLDEN.read_bytes()
