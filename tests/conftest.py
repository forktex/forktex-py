"""Test fixtures."""

import os
import tempfile
import shutil
from pathlib import Path

import pytest


@pytest.fixture
def temp_dir():
    """Create a temporary directory."""
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def temp_dir_with_files(temp_dir):
    """Create a temporary directory with sample files."""
    # Create some files
    (Path(temp_dir) / "main.py").write_text("print('hello')\n")
    (Path(temp_dir) / "utils.py").write_text("def add(a, b):\n    return a + b\n")
    (Path(temp_dir) / "README.md").write_text("# Test Project\n")
    sub = Path(temp_dir) / "src"
    sub.mkdir()
    (sub / "app.py").write_text("from utils import add\n")
    (sub / "__init__.py").write_text("")
    return temp_dir


@pytest.fixture
def temp_git_repo(temp_dir):
    """Create a temporary git repository."""
    import subprocess

    subprocess.run(["git", "init"], cwd=temp_dir, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=temp_dir,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"], cwd=temp_dir, capture_output=True
    )
    (Path(temp_dir) / "file.txt").write_text("hello\n")
    subprocess.run(["git", "add", "."], cwd=temp_dir, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"], cwd=temp_dir, capture_output=True
    )
    return temp_dir
