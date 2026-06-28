from __future__ import annotations

import pytest

from coruscant.apps import cli


def test_cli_sources(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["sources"]) == 0
    out = capsys.readouterr().out
    assert "sec_edgar" in out
    assert "patents" in out


def test_cli_companies(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["companies"]) == 0
    out = capsys.readouterr().out
    assert "apple" in out
    assert "tesla" in out


def test_cli_no_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert "usage" in out.lower()


def test_cli_parser_exposes_all_commands() -> None:
    parser = cli.build_parser()
    namespace = parser.parse_args(["serve", "--port", "9001"])
    assert namespace.port == 9001
    assert namespace.func is cli.cmd_serve
