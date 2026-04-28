"""Standard install mode is not implemented — should error out cleanly."""
from __future__ import annotations


def test_standard_mode_exits_with_error(setup_env):
    answers = "1\n"  # pick standard mode

    result = setup_env.runner.invoke(
        setup_env.main,
        ["setup", "--data-root", str(setup_env.data_root)],
        input=answers,
    )

    assert result.exit_code == 1
    # settings.json must not be written when we bail out at install_mode step
    assert not (setup_env.data_root / "settings.json").exists()
    # The error message should explain the situation
    combined = (result.stdout or "") + (result.stderr or "")
    assert "standard" in combined.lower()
    assert "not implemented" in combined.lower() or "isn't on pypi" in combined.lower()
