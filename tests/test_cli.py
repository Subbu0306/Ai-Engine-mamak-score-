from pathlib import Path

from mamakscore.cli import main


def test_check_config_offline(capsys):
    code = main(
        [
            "check-config",
            "--rubric",
            str(Path(__file__).parents[1] / "src/mamakscore/data/mamakscore-v3.yaml"),
        ]
    )
    assert code == 0 and "offline" in capsys.readouterr().out
