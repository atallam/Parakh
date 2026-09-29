from parakh.agents.summarizer import summarize
from parakh.cli import main
from parakh.prompts import render_prompt

VALID = '{"title": "Hello", "bullets": ["one point"], "confidence": 0.9}'


def test_prompt_renders() -> None:
    system, user = render_prompt("summarize", text="some text")
    assert "JSON" in system
    assert "some text" in user


def test_agent_with_fake_llm(fake_llm) -> None:
    llm = fake_llm(VALID)
    summary = summarize("some text", client=llm.client())
    assert summary is not None
    assert summary.title == "Hello"


def test_cli_doctor(capsys) -> None:
    assert main(["doctor"]) == 0
    assert "parakh" in capsys.readouterr().out
