from __future__ import annotations

import subprocess
from pathlib import Path

from core.git_remote import origin_https_url


def test_origin_https_url_from_git_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "remote", "add", "origin", "git@github.com:org/demo.git"],
        check=True,
        capture_output=True,
    )
    assert origin_https_url(str(repo)) == "https://github.com/org/demo"


def test_origin_https_url_https_remote(tmp_path: Path) -> None:
    repo = tmp_path / "repo2"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "remote",
            "add",
            "origin",
            "https://github.com/acme/widget.git",
        ],
        check=True,
        capture_output=True,
    )
    assert origin_https_url(str(repo)) == "https://github.com/acme/widget"


def test_origin_https_url_non_repo(tmp_path: Path) -> None:
    assert origin_https_url(str(tmp_path / "nope")) is None
