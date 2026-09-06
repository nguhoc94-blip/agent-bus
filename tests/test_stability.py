"""Tests for app/stability.py."""

from __future__ import annotations

from pathlib import Path

from app.stability import (
    has_temp_extension, size_stable, wait_until_readable,
)


TEMP = [".crdownload", ".part", ".tmp", ".download", ".partial"]


def test_temp_extension_detection(tmp_path: Path):
    assert has_temp_extension(tmp_path / "foo.crdownload", TEMP)
    assert has_temp_extension(tmp_path / "bar.PART", TEMP)
    assert has_temp_extension(tmp_path / "baz.Tmp", TEMP)
    assert not has_temp_extension(tmp_path / "real.md", TEMP)
    assert not has_temp_extension(tmp_path / "doc.pdf", TEMP)


def test_size_stable_constant_size(tmp_path: Path):
    f = tmp_path / "stable.md"
    f.write_bytes(b"hello world")
    fake_sleeps: list = []
    assert size_stable(f, checks=3, interval_s=0.01,
                       sleep=lambda s: fake_sleeps.append(s)) is True
    assert len(fake_sleeps) == 2  # checks-1 sleeps


def test_size_stable_growing(tmp_path: Path):
    f = tmp_path / "growing.md"
    f.write_bytes(b"a")

    sizes = iter([10, 20, 30])
    calls = {"i": 0}

    def fake_sleep(_s):
        # Grow file between checks to simulate ongoing write
        nxt = next(sizes)
        f.write_bytes(b"x" * nxt)
        calls["i"] += 1

    assert size_stable(f, checks=3, interval_s=0.01, sleep=fake_sleep) is False


def test_size_stable_missing_file(tmp_path: Path):
    ghost = tmp_path / "ghost.md"
    assert size_stable(ghost, checks=2, interval_s=0.01, sleep=lambda s: None) is False


def test_wait_until_readable_success(tmp_path: Path):
    f = tmp_path / "r.md"
    f.write_text("x", encoding="utf-8")
    assert wait_until_readable(f, max_retries=2, delay_s=0.01, sleep=lambda s: None)


def test_wait_until_readable_exhausts(tmp_path: Path):
    ghost = tmp_path / "ghost.md"
    slept = []
    assert wait_until_readable(
        ghost, max_retries=3, delay_s=0.01, sleep=lambda s: slept.append(s)) is False
    assert len(slept) == 2  # attempts - 1
