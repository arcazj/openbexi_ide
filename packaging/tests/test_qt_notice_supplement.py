"""Fail closed on missing, altered or escaping installed license artifacts."""

import importlib.util
import json
from pathlib import Path
import shutil

import pytest


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("qt_notices", ROOT / "scripts/verify_qt_notice_supplement.py")
notices = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notices)


@pytest.fixture
def installed(tmp_path):
    shutil.copytree(ROOT / "src" / notices.PREFIX, tmp_path / notices.PREFIX)
    return tmp_path


def test_complete_exact_upstream_notice_bytes(installed):
    result = notices.verify_notices(installed)
    assert len(result["files"]) == 7
    assert not result["license_compatibility_qualified"]
    assert not result["complete_qt_third_party_review"]


def test_modified_notice_fails(installed):
    (installed / notices.PREFIX / "LGPL-3.0-only.txt").write_text("truncated license")
    with pytest.raises(ValueError, match="notice_bytes_differ"):
        notices.verify_notices(installed)


def test_unreviewed_extra_member_fails(installed):
    (installed / notices.PREFIX / "implementation.cpp").write_text("unexpected code")
    with pytest.raises(ValueError, match="notice_members_differ"):
        notices.verify_notices(installed)


def test_missing_notice_fails(installed):
    (installed / notices.PREFIX / "PSF-3.7.0.txt").unlink()
    with pytest.raises(ValueError, match="notice_members_differ"):
        notices.verify_notices(installed)


def test_omitted_required_notice_fails(installed):
    path = installed / notices.PREFIX / "manifest.json"
    data = json.loads(path.read_text())
    data["files"].pop()
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="required_files_differ"):
        notices.verify_notices(installed)


def test_symlink_escape_fails(installed, tmp_path):
    outside = tmp_path.parent / "outside-notice.txt"
    outside.write_text("not a notice")
    path = installed / notices.PREFIX / "PSF-3.7.0.txt"
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(ValueError, match="escapes"):
        notices.verify_notices(installed)


def test_wrong_upstream_wheel_fails_before_inspecting_installed_bytes(installed, tmp_path):
    manifest = notices.verify_notices(installed)
    item = manifest["dependencies"][0]
    wrong = tmp_path / item["wheel"]
    wrong.write_bytes(b"not the pinned Qt wheel")
    with pytest.raises(ValueError, match="wheel_identity_differs"):
        notices.verify_dependency(installed, wrong, item)
