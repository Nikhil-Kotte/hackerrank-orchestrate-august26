import os

from router.cli import load_env


def test_load_env_reads_padded_and_quoted_values(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "# comment\n"
        "\n"
        "OPENROUTER_API_KEY = sk-or-v1-test\n"
        'OPENROUTER_MODEL="google/gemini-2.5-flash"\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)

    load_env(env)

    assert os.environ["OPENROUTER_API_KEY"] == "sk-or-v1-test"
    assert os.environ["OPENROUTER_MODEL"] == "google/gemini-2.5-flash"


def test_load_env_does_not_override_the_real_environment(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("OPENROUTER_API_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setenv("OPENROUTER_API_KEY", "from-shell")

    load_env(env)

    assert os.environ["OPENROUTER_API_KEY"] == "from-shell"


def test_load_env_is_a_noop_when_the_file_is_missing(tmp_path):
    load_env(tmp_path / "absent.env")
