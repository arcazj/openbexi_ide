"""Inventory the installed Windows qualification environment and its shipped notices."""

import argparse
from collections import Counter
from hashlib import sha256
from importlib import metadata
import json
from pathlib import Path
import subprocess
from uuid import NAMESPACE_URL, uuid5
from zipfile import ZIP_DEFLATED, ZipFile


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def normalize(name):
    return name.casefold().replace("_", "-")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("installation", "scanner", "cache", "raw", "archive", "report"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    receipt = json.loads((args.installation / "result.json").read_bytes())
    assert receipt["passed"] and len(receipt["verified_wheels"]) == 6
    args.raw.mkdir(parents=True, exist_ok=True)
    packages = args.installation / "venv/Lib/site-packages"
    subjects = {}
    wheels = {
        normalize(name.split("-")[0]): value
        for name, value in receipt["artifacts"].items()
    }
    wheels.update(
        {
            normalize(name): row["sha256"]
            for name, row in receipt["online_dependencies"].items()
        }
    )
    for dist in metadata.distributions(path=[str(packages)]):
        name = normalize(dist.metadata["Name"])
        files = {}
        native = {}
        for member in dist.files or ():
            path = Path(dist.locate_file(member))
            if not path.is_file():
                continue
            lower = member.name.lower()
            if (
                lower.startswith(
                    ("license", "licence", "copying", "notice", "copyright")
                )
                or "/licenses/" in member.as_posix().lower()
            ):
                files[member.as_posix()] = digest(path)
            if path.suffix.lower() in (".dll", ".pyd", ".exe"):
                native[member.as_posix()] = digest(path)
        subjects[name] = dict(
            version=dist.version,
            expression=dist.metadata.get("License-Expression"),
            classifiers=[
                c
                for c in dist.metadata.get_all("Classifier", [])
                if c.startswith("License ::")
            ],
            notices=files,
            native_binaries=native,
        )
    assert len(subjects) == 14
    expected = {normalize(n.split("-")[0]) for n in receipt["verified_wheels"]}
    expected.update(normalize(n) for n in receipt["online_dependencies"])
    assert set(subjects) == expected | {"pip"}
    version = subprocess.check_output(
        [args.scanner, "--version"], text=True
    ).splitlines()[0]
    flags = [
        args.scanner,
        "fs",
        "--cache-dir",
        args.cache,
        "--offline-scan",
        "--skip-db-update",
        "--skip-java-db-update",
        "--no-progress",
        "--scanners",
        "vuln",
    ]
    helptext = subprocess.check_output([args.scanner, "fs", "--help"], text=True)
    for opt in ("--disable-telemetry", "--skip-version-check"):
        if opt in helptext:
            flags.append(opt)
    discovery = args.raw / "filesystem.cdx.json"
    sbom = args.raw / "installed.cdx.json"
    advisory = args.raw / "known-advisories.json"
    vendor_file = packages / "pip/_vendor/vendor.txt"
    vendors = {
        normalize(name): version
        for line in vendor_file.read_text(encoding="utf-8").splitlines()
        if "==" in line
        for name, version in [line.strip().split("==", 1)]
    }
    components = {}
    for origin, versions in (
        ("installed", {k: v["version"] for k, v in subjects.items()}),
        ("pip/_vendor/vendor.txt", vendors),
    ):
        for name, version_number in versions.items():
            purl = f"pkg:pypi/{name}@{version_number}"
            component = components.setdefault(
                purl,
                dict(
                    type="library",
                    name=name,
                    version=version_number,
                    purl=purl,
                    properties=[],
                    **{"bom-ref": purl},
                ),
            )
            component["properties"].append(
                dict(name="openbexi:evidence:origin", value=origin)
            )
            if origin == "installed" and name in wheels:
                component["hashes"] = [dict(alg="SHA-256", content=wheels[name])]
            if origin == "installed" and subjects[name]["expression"]:
                component["licenses"] = [dict(expression=subjects[name]["expression"])]
    # An active distribution comprises its actual installed metadata and its known wheel digest.
    # The original file scanner may discover zero components on an installed Windows venv.
    # Explicit package URLs let the advisory scanner evaluate that exact set.
    qt = subprocess.check_output(
        [
            args.installation / "venv/Scripts/python.exe",
            "-I",
            "-c",
            "from PySide6.QtCore import qVersion;print(qVersion())",
        ],
        text=True,
    ).strip()
    components["pkg:generic/qt@" + qt] = dict(
        type="framework",
        name="Qt",
        version=qt,
        purl="pkg:generic/qt@" + qt,
        **{"bom-ref": "pkg:generic/qt@" + qt},
    )
    model = dict(
        bomFormat="CycloneDX",
        specVersion="1.6",
        version=1,
        serialNumber="urn:uuid:"
        + str(
            uuid5(
                NAMESPACE_URL, "openbexi:" + digest(args.installation / "result.json")
            )
        ),
        components=list(components.values()),
    )
    sbom.write_bytes(encode(model))
    with (args.raw / "scanner.log").open("wb") as log:
        subprocess.run(
            [*flags, "--format", "cyclonedx", "--output", discovery, packages],
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
        )
        subprocess.run(
            [
                args.scanner,
                "sbom",
                *flags[2:],
                "--list-all-pkgs",
                "--format",
                "json",
                "--output",
                advisory,
                sbom,
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
        )
    discovered = json.loads(discovery.read_bytes()).get("components", [])
    observed = {normalize(c["name"]) for c in model["components"]}
    missing = sorted(set(subjects) - observed)
    reports = json.loads(advisory.read_bytes()).get("Results", [])
    advisory_packages = {
        (normalize(p["Name"]), p["Version"])
        for target in reports
        for p in target.get("Packages", [])
    }
    if not all(
        (name, dist["version"]) in advisory_packages for name, dist in subjects.items()
    ):
        raise ValueError(
            "Advisory database did not account for every installed distribution"
        )
    matches = {
        (row["VulnerabilityID"], row["PkgName"], row["InstalledVersion"]): row
        for report in reports
        for row in report.get("Vulnerabilities", [])
    }
    rows = [
        {
            k: v.get(k)
            for k in (
                "VulnerabilityID",
                "PkgName",
                "InstalledVersion",
                "Severity",
                "FixedVersion",
                "Status",
            )
        }
        for _, v in sorted(matches.items())
    ]
    assert not missing
    contents = {
        "installed.cdx.json": sbom.read_bytes(),
        "initial-file-discovery.cdx.json": discovery.read_bytes(),
        "advisory-matches.json": encode(rows),
        "installed-notices-and-binaries.json": encode(subjects),
    }
    with ZipFile(args.archive, "w", ZIP_DEFLATED) as archive:
        for name, blob in contents.items():
            archive.writestr(name, blob)
    with ZipFile(args.archive) as archive:
        assert archive.testzip() is None and all(
            archive.read(n) == b for n, b in contents.items()
        )
    summary = dict(
        status="COLLECTED",
        subjects=receipt["subjects"],
        scanner=version,
        scanner_binary_sha256=digest(args.scanner),
        inventory_harness_sha256=digest(Path(__file__)),
        installation_sha256=digest(args.installation / "result.json"),
        components=len(components),
        initial_file_scanner_components=len(discovered),
        pip_vendor_manifest_sha256=digest(vendor_file),
        package_versions_recognized_by_advisory_scan=len(advisory_packages),
        pip_vendored_versions=vendors,
        qt_runtime_version=qt,
        distributions={
            n: dict(
                version=v["version"],
                notices=len(v["notices"]),
                native_binaries=len(v["native_binaries"]),
            )
            for n, v in sorted(subjects.items())
        },
        native_binary_hashes=sum(len(v["native_binaries"]) for v in subjects.values()),
        installed_distributions_missing_from_scanner=missing,
        distinct_advisory_package_versions=len(rows),
        advisory_severities=dict(Counter(r["Severity"] for r in rows)),
        with_upstream_fix=sum(bool(r["FixedVersion"]) for r in rows),
        raw_findings_sha256=digest(advisory),
        archive=args.archive.name,
        archive_sha256=digest(args.archive),
        members={n: sha256(b).hexdigest() for n, b in contents.items()},
        scope="The six staged Windows products, seven online dependencies and bootstrap pip are established by installed metadata. The SBOM also includes pip-declared vendored dependencies and the Qt version reported by the installed runtime. Native binaries and notices have individual hashes. The raw file-discovery scan and advisory search of the explicit SBOM are separate. Embedded native library code requires independent review.",
        release_disposition="OPEN_INDEPENDENT_REVIEW",
        risk_exceptions=[],
    )
    args.report.write_bytes(encode(summary))
    print(
        "Windows inventory",
        len(subjects),
        "distributions",
        summary["native_binary_hashes"],
        "native files",
        len(rows),
        "advisory matches",
    )


if __name__ == "__main__":
    main()
