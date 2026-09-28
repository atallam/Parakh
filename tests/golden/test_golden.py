"""Golden dataset: assert key fields and output shape, not just text (C5.2, C5.4)."""

from pathlib import Path

import pytest
import yaml

from parakh.agents.summarizer import summarize

CASES = sorted((Path(__file__).parent / "cases").glob("*.yaml"))


@pytest.mark.parametrize("case_path", CASES, ids=lambda p: p.stem)
def test_golden_case(case_path: Path, fake_llm) -> None:
    case = yaml.safe_load(case_path.read_text(encoding="utf-8"))
    llm = fake_llm(case["llm_reply"])
    result = summarize(case["input"], client=llm.client())
    assert result is not None
    got = result.model_dump()
    expected_fields = case["expected_fields"]
    assert set(got) == set(expected_fields), "output shape changed"
    for name, expected in expected_fields.items():
        assert got[name] == expected, name
    for forbidden in case.get("prompt_must_not_contain", []):
        assert all(str(forbidden) not in call["prompt"] for call in llm.calls), forbidden


def test_there_are_golden_cases() -> None:
    assert CASES, "add at least one case under tests/golden/cases/"
