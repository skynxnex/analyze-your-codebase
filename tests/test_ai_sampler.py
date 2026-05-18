"""Tests for repoaudit.ai.sampler."""

from __future__ import annotations

from pathlib import Path

import pytest

from repoaudit.ai.sampler import sample, _read_truncated, _MAX_LINES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(tmp_path: Path, rel: str, content: str) -> Path:
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# _read_truncated
# ---------------------------------------------------------------------------


class TestReadTruncated:
    def test_short_file_returned_in_full(self, tmp_path: Path) -> None:
        f = _write(tmp_path, "short.py", "a\nb\nc\n")
        result = _read_truncated(f)
        assert result == "a\nb\nc"

    def test_file_at_limit_not_truncated(self, tmp_path: Path) -> None:
        content = "\n".join(str(i) for i in range(_MAX_LINES))
        f = _write(tmp_path, "exact.py", content)
        result = _read_truncated(f)
        assert "... (truncated)" not in result
        assert result == content

    def test_file_over_limit_is_truncated(self, tmp_path: Path) -> None:
        lines = [str(i) for i in range(_MAX_LINES + 10)]
        f = _write(tmp_path, "long.py", "\n".join(lines))
        result = _read_truncated(f)
        assert result.endswith("... (truncated)")
        # Only _MAX_LINES lines before the truncation marker.
        kept = result.replace("\n... (truncated)", "").splitlines()
        assert len(kept) == _MAX_LINES

    def test_nonexistent_file_returns_empty_string(self, tmp_path: Path) -> None:
        result = _read_truncated(tmp_path / "ghost.py")
        assert result == ""


# ---------------------------------------------------------------------------
# Entry-point detection
# ---------------------------------------------------------------------------


class TestEntryPointDetection:
    @pytest.mark.parametrize(
        "entry_name",
        ["manage.py", "app.py", "main.py", "main.kt", "main.go", "Program.cs", "index.ts"],
    )
    def test_finds_entry_point_for_each_language(self, tmp_path: Path, entry_name: str) -> None:
        _write(tmp_path, entry_name, "# entry point\n")
        result = sample(tmp_path)
        roles = {s["role"] for s in result}
        assert "entry_point" in roles
        entry = next(s for s in result if s["role"] == "entry_point")
        assert entry["path"] == entry_name

    def test_no_entry_point_returns_only_sources(self, tmp_path: Path) -> None:
        _write(tmp_path, "app/service.py", "x = 1\n")
        result = sample(tmp_path)
        assert all(s["role"] != "entry_point" for s in result)

    def test_empty_repo_returns_empty_list(self, tmp_path: Path) -> None:
        result = sample(tmp_path)
        assert result == []


# ---------------------------------------------------------------------------
# Excluded directories
# ---------------------------------------------------------------------------


class TestExcludedDirs:
    @pytest.mark.parametrize(
        "excluded_dir",
        [".venv", "node_modules", "__pycache__", ".git", "venv"],
    )
    def test_excluded_dir_files_not_sampled(self, tmp_path: Path, excluded_dir: str) -> None:
        _write(tmp_path, f"{excluded_dir}/secret.py", "password = 'hunter2'\n")
        result = sample(tmp_path)
        paths = [s["path"] for s in result]
        assert not any(excluded_dir in p for p in paths)

    def test_non_excluded_files_are_sampled(self, tmp_path: Path) -> None:
        _write(tmp_path, "app/views.py", "def index(): pass\n")
        result = sample(tmp_path)
        paths = [s["path"] for s in result]
        assert any("views.py" in p for p in paths)


# ---------------------------------------------------------------------------
# Max file count
# ---------------------------------------------------------------------------


class TestMaxSourceFiles:
    def test_at_most_three_source_files_plus_entry_and_test(self, tmp_path: Path) -> None:
        _write(tmp_path, "main.py", "# entry\n")
        for i in range(10):
            _write(tmp_path, f"app/module_{i}.py", f"x = {i}\n")
        _write(tmp_path, "tests/test_something.py", "def test_x(): pass\n")

        result = sample(tmp_path)
        sources = [s for s in result if s["role"] == "source"]
        assert len(sources) <= 3

    def test_entry_point_not_duplicated_as_source(self, tmp_path: Path) -> None:
        _write(tmp_path, "main.py", "# entry\n")
        result = sample(tmp_path)
        entry_count = sum(1 for s in result if s["path"] == "main.py")
        assert entry_count == 1


# ---------------------------------------------------------------------------
# Test file detection
# ---------------------------------------------------------------------------


class TestTestFileSampling:
    def test_finds_pytest_test_file(self, tmp_path: Path) -> None:
        _write(tmp_path, "tests/test_foo.py", "def test_bar(): pass\n")
        result = sample(tmp_path)
        test_samples = [s for s in result if s["role"] == "test"]
        assert len(test_samples) == 1

    def test_at_most_one_test_file(self, tmp_path: Path) -> None:
        for i in range(5):
            _write(tmp_path, f"tests/test_thing_{i}.py", f"def test_{i}(): pass\n")
        result = sample(tmp_path)
        test_samples = [s for s in result if s["role"] == "test"]
        assert len(test_samples) <= 1
