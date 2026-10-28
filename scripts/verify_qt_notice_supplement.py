"""Verify installed notice delivery and exact optional Qt wheel byte identities.

This is a narrow packaging check. It cannot establish complete Qt third-party
license coverage, licensing compatibility or implemented-system security.
"""

import argparse
from email import message_from_bytes
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zipfile


PREFIX = Path("openbexi_ide/licenses/qt_for_python_6_10_3")
SOURCE_COMMIT = "863e6b6e6269fbd401db06e2066119b9014fcf0d"
REQUIRED = {
    "LGPL-3.0-only.txt", "GPL-2.0-only.txt", "GPL-3.0-only.txt",
    "PSF-3.7.0.txt", "libshiboken-attribution.json",
    "signature-attribution.json", "PSF-bufferprocs-3.7.0.txt",
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def safe_file(root, relative):
    path = PurePosixPath(relative)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError("unsafe_notice_or_wheel_path")
    resolved = (root / path).resolve(strict=True)
    if not resolved.is_relative_to(root.resolve(strict=True)) or not resolved.is_file():
        raise ValueError("installed_path_escapes_or_is_not_a_file")
    return resolved


def verify_notices(site_packages):
    root = Path(site_packages)
    manifest_file = safe_file(root, (PREFIX / "manifest.json").as_posix())
    manifest = json.loads(manifest_file.read_text())
    if (
        manifest.get("schema") != "openbexi.qt-python-notice-supplement/1"
        or manifest.get("upstream_commit") != SOURCE_COMMIT
        or manifest.get("complete_qt_third_party_review") is not False
        or manifest.get("license_compatibility_qualified") is not False
    ):
        raise ValueError("notice_manifest_identity_or_scope_differs")
    entries = manifest["files"]
    if len(entries) != len(REQUIRED) or {e["installed_name"] for e in entries} != REQUIRED:
        raise ValueError("notice_manifest_required_files_differ")
    if {p.name for p in manifest_file.parent.iterdir()} != REQUIRED | {"manifest.json"}:
        raise ValueError("installed_notice_members_differ")
    for entry in entries:
        if not re.fullmatch(r"[0-9a-f]{40}", entry["source_blob"]):
            raise ValueError("notice_source_blob_missing")
        raw = safe_file(root, (PREFIX / entry["installed_name"]).as_posix()).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if (
            len(raw) != entry["bytes"] or sha(raw) != entry["sha256"]
            or blob != entry.get("installed_blob", entry["source_blob"])
        ):
            raise ValueError("installed_notice_bytes_differ:" + entry["installed_name"])
    return manifest


def verify_dependency(site_packages, wheel, dependency):
    wheel = Path(wheel)
    raw = wheel.read_bytes()
    if (
        wheel.name != dependency["wheel"] or len(raw) != dependency["wheel_bytes"]
        or sha(raw) != dependency["wheel_sha256"]
    ):
        raise ValueError("qt_wheel_identity_differs")
    root = Path(site_packages)
    checked = 0
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        if len(set(names)) != len(names) or len(names) != dependency["upstream_wheel_members"]:
            raise ValueError("qt_wheel_members_differ")
        metadata_names = [n for n in names if n.endswith(".dist-info/METADATA")]
        if len(metadata_names) != 1:
            raise ValueError("qt_wheel_metadata_ambiguous")
        metadata = message_from_bytes(archive.read(metadata_names[0]))
        def canonical(value):
            return re.sub(r"[-_.]+", "-", value).lower()
        if (
            canonical(metadata["Name"]) != canonical(dependency["name"])
            or metadata["Version"] != dependency["version"]
        ):
            raise ValueError("qt_wheel_metadata_differs")
        for member in archive.infolist():
            if member.is_dir():
                continue
            # pip legitimately rewrites RECORD when adding its installation
            # metadata. Every other member of these two pinned wheels is byte
            # preserving; neither wheel has a .data spreading directory.
            if member.filename.endswith(".dist-info/RECORD"):
                continue
            installed = safe_file(root, member.filename)
            if sha(installed.read_bytes()) != sha(archive.read(member)):
                raise ValueError("installed_qt_bytes_differ:" + member.filename)
            checked += 1
    return {"name": dependency["name"], "version": dependency["version"],
            "wheel_sha256": dependency["wheel_sha256"], "installed_members_verified": checked}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-packages", type=Path, required=True)
    parser.add_argument("--wheel-directory", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    manifest = verify_notices(args.site_packages)
    dependencies = []
    if args.wheel_directory:
        dependencies = [verify_dependency(args.site_packages, args.wheel_directory / item["wheel"], item)
                        for item in manifest["dependencies"]]
    report = {
        "schema": "openbexi.qt-python-notice-delivery/1",
        "notices_verified": len(manifest["files"]), "notice_source": SOURCE_COMMIT,
        "installed_dependencies": dependencies,
        "direct_notice_delivery_passed": True,
        "complete_qt_third_party_review": False,
        "license_compatibility_qualified": False,
        "full_v08_qualified": False,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
