"""pure_fts mode — English multi-word exact-match probe set."""
from pathlib import Path

from memory_talk_v2.tests.search._runner import load_probes, run_case


PROBES_PATH = Path(__file__).parent / "probes.json"


def test_quality(app_client, baselines):
    probes = load_probes(PROBES_PATH)
    run_case(app_client, baselines, "pure_fts.en_multi_word", probes)
