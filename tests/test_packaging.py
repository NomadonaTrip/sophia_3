"""The package skeleton must be importable and declare its one dependency."""
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_interfaces_package_importable():
    import interfaces  # noqa: F401


def test_tools_package_importable():
    import tools  # noqa: F401


def test_pyyaml_is_declared_and_importable():
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    deps = data["project"]["dependencies"]
    assert any(d.lower().startswith("pyyaml") for d in deps), deps
    import yaml  # noqa: F401


def test_env_example_exists_and_env_is_ignored():
    assert (REPO_ROOT / ".env.example").is_file()
    ignored = (REPO_ROOT / ".gitignore").read_text().splitlines()
    assert ".env" in ignored
