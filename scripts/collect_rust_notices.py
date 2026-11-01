"""Collect/check exact Cargo license notices and the MPL source used by desktop builds.

Collection needs `cargo fetch --locked` for the requested targets. Checking is
offline and needs no Rust toolchain; release packagers can call check_bundle().
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ("x86_64-pc-windows-msvc", "x86_64-unknown-linux-gnu", "aarch64-apple-darwin")
INPUTS = ("LICENSE", "rust-toolchain.toml", "native/Cargo.lock", "native/Cargo.toml", "native/crates/app/Cargo.toml", "native/crates/core/Cargo.toml")
CHOICES = {
    "MIT": "MIT", "Apache-2.0": "Apache-2.0", "ISC": "ISC", "MPL-2.0": "MPL-2.0",
    "Unicode-3.0": "Unicode-3.0", "Apache-2.0 AND MIT": "Apache-2.0 AND MIT",
    "Apache-2.0 WITH LLVM-exception": "Apache-2.0 WITH LLVM-exception",
    "(MIT OR Apache-2.0) AND Unicode-3.0": "MIT AND Unicode-3.0",
    **dict.fromkeys(("MIT OR Apache-2.0", "Apache-2.0 OR MIT", "MIT/Apache-2.0", "Apache-2.0/MIT",
                    "MIT OR Apache-2.0 OR Zlib", "Zlib OR Apache-2.0 OR MIT", "Unlicense OR MIT",
                    "Apache-2.0 WITH LLVM-exception OR Apache-2.0 OR MIT"), "MIT"),
    "CC0-1.0 OR MIT-0 OR Apache-2.0": "Apache-2.0",
}
NOTICE_NAME = re.compile(r"^(?:licen[cs]e|copying|notice|copyright|authors)(?:[._-]|$)", re.I)
CODE_SUFFIXES = {".rs", ".c", ".h", ".cpp", ".hpp", ".py", ".png", ".dll", ".lib"}
ARCHIVE_ONLY_ASSETS = {
    ("libloading", "0.8.9"): {"tests/nagisa32.dll", "tests/nagisa64.dll"},
    ("system-deps", "6.2.2"): {"src/tests/lib/libteststatic.a"},
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical_text(data):
    data.decode("utf-8")
    return data.replace(b"\r\n", b"\n")


def relative_path(value):
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value or ":" in value:
        raise ValueError(f"Unsafe notice path: {value!r}")
    return path


def crate_contents(archive, expected_sha256, name, version):
    data = archive.read_bytes()
    if digest(data) != expected_sha256:
        raise ValueError(f"Crate checksum mismatch: {name}-{version}")
    files = {}
    prefix = f"{name}-{version}/"
    with tarfile.open(archive, "r:gz") as source:
        for member in source:
            if not member.name.startswith(prefix):
                raise ValueError(f"Unexpected crate member: {member.name}")
            path = str(relative_path(member.name[len(prefix):]))
            if member.isdir():
                continue
            if not member.isfile() or member.size > 16 * 1024 * 1024 or path in files:
                raise ValueError(f"Unsupported crate member: {member.name}")
            files[path] = source.extractfile(member).read()
    return files


def package_notices(files, package):
    chosen = {path: data for path, data in files.items()
              if NOTICE_NAME.match(PurePosixPath(path).name) and PurePosixPath(path).suffix.lower() not in CODE_SUFFIXES}
    if package.get("license-file"):
        path = str(relative_path(package["license-file"]))
        chosen[path] = files[path]
    for data in chosen.values():
        data.decode("utf-8")
    return chosen


def target_graph(root, cargo, target):
    result = subprocess.run([cargo, "tree", "--manifest-path", str(root/"native/Cargo.toml"), "--locked", "--offline",
                             "-p", "mbdyn-studio-desktop", "--target", target, "--edges", "normal,build",
                             "--prefix", "none", "--format", "{p}|{l}"], check=True, capture_output=True, text=True, encoding="utf-8")
    packages = set()
    for line in result.stdout.splitlines():
        match = re.match(r"([^ ]+) v([^ |]+)", line)
        if not match:
            raise ValueError(f"Unexpected cargo tree output: {line}")
        packages.add(match.groups())
    return packages


def check_bundle(notices, target=None, source_root=None):
    """Validate a copied bundle offline; optionally require current source inputs."""
    notices = Path(notices)
    manifest = json.loads((notices/"manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != "kinemeld-rust-notices/1":
        raise ValueError("Unsupported Rust notice manifest.")
    if set(manifest["sourceInputs"]) != set(INPUTS) or not manifest["targets"] or not set(manifest["targets"]) <= set(TARGETS):
        raise ValueError("Rust notice source inputs or release targets are incomplete/unreviewed.")
    if target and target not in manifest["targets"]:
        raise ValueError(f"Rust notices do not cover {target}.")
    known_files = set(manifest["files"])
    actual_files = {p.relative_to(notices).as_posix() for p in notices.rglob("*") if p.is_file() and p != notices/"manifest.json"}
    if actual_files != known_files:
        raise ValueError(f"Rust notice inventory differs: missing={sorted(known_files-actual_files)}, extra={sorted(actual_files-known_files)}")
    for name, expected in manifest["files"].items():
        relative_path(name)
        file = notices/name
        if file.is_symlink() or digest(file.read_bytes()) != expected:
            raise ValueError(f"Rust notice checksum mismatch: {name}")
    sdk = json.loads((notices/"upstream/webview2-sdk.json").read_text(encoding="utf-8"))
    if sdk != manifest["webview2Sdk"] or sdk["license"] != "BSD-3-Clause":
        raise ValueError("WebView2 SDK provenance differs from the reviewed notice record.")
    for name, expected in sdk["noticeFiles"].items():
        relative_path(name)
        if name not in known_files or digest((notices/name).read_bytes()) != expected:
            raise ValueError(f"Missing WebView2 SDK notice: {name}")
    for path, expected in manifest["sourceInputs"].items():
        relative_path(path)
        data = (notices/"source-inputs"/path).read_bytes()
        if digest(data) != expected:
            raise ValueError(f"Rust source input was altered: {path}")
        if source_root is not None and digest(canonical_text((Path(source_root)/path).read_bytes())) != expected:
            raise ValueError(f"Rust notices are stale; regenerate after changing {path}.")
    locked = {(p["name"],p["version"]): p for p in tomllib.loads((notices/"source-inputs/native/Cargo.lock").read_text(encoding="utf-8"))["package"]}
    components = {f"{p['name']}@{p['version']}": p for p in manifest["components"]}
    if len(components) != len(manifest["components"]):
        raise ValueError("Duplicate Rust components.")
    aggregate = (notices/"THIRD_PARTY_RUST.txt").read_bytes()
    for key, item in components.items():
        lock = locked[(item["name"],item["version"])]
        if lock.get("checksum") != item["crateSha256"] or CHOICES.get(item["licenseDeclared"]) != item["licenseSelected"]:
            raise ValueError(f"Unreviewed Rust license or source identity: {key}")
        if not item["notices"]:
            raise ValueError(f"Missing Rust license notice: {key}")
        for notice in item["notices"]:
            start, length = notice["aggregateOffset"], notice["byteLength"]
            if start < 0 or length <= 0 or digest(aggregate[start:start+length]) != notice["sha256"]:
                raise ValueError(f"Missing or altered Rust attribution text: {key}/{notice['sourcePath']}")
        if item["licenseSelected"] == "MPL-2.0":
            source = item.get("sourceArchive")
            if not source or str(relative_path(source)) not in known_files or digest((notices/source).read_bytes()) != item["crateSha256"]:
                raise ValueError(f"Missing exact MPL source: {key}")
        expected_targets = {platform for platform, graph in manifest["targets"].items() if key in graph["components"]}
        if not expected_targets or set(item["targets"]) != expected_targets:
            raise ValueError(f"Incorrect Rust component target coverage: {key}")
    for platform, graph in manifest["targets"].items():
        relative_path(graph["graph"])
        if not graph["components"] or len(set(graph["components"])) != len(graph["components"]):
            raise ValueError(f"Empty or duplicate Rust target component inventory: {platform}")
        if (notices/graph["graph"]).read_text(encoding="utf-8").splitlines() != graph["components"]:
            raise ValueError(f"Rust target graph inventory differs: {platform}")
        for key in graph["components"]:
            if key not in components or platform not in components[key]["targets"]:
                raise ValueError(f"Incomplete Rust target coverage: {platform}/{key}")
    return manifest


def check_compiler(manifest, rustc="rustc"):
    def identity(text):
        fields = dict(line.split(": ",1) for line in text.splitlines() if ": " in line)
        return fields.get("release"), fields.get("commit-hash")
    expected = identity(manifest["toolchain"]["rustcVerbose"])
    actual = identity(subprocess.check_output([rustc,"-vV"],text=True,encoding="utf-8"))
    if None in expected or actual != expected:
        raise ValueError(f"Rust compiler identity differs from the audited library notices: expected {expected}, got {actual}.")


def collect(root, output, cargo, cargo_home, rustc, targets):
    root, output, cargo_home = Path(root), Path(output), Path(cargo_home)
    locked = {(p["name"],p["version"]): p for p in tomllib.loads((root/"native/Cargo.lock").read_text(encoding="utf-8"))["package"]}
    upstream_file = output/"upstream/manifest.json"
    upstream = json.loads(upstream_file.read_text(encoding="utf-8"))
    sdk = json.loads((output/"upstream/webview2-sdk.json").read_text(encoding="utf-8"))
    payloads = {p.relative_to(output).as_posix(): p.read_bytes() for p in (output/"upstream").rglob("*") if p.is_file()}
    payloads["README.md"] = canonical_text((output/"README.md").read_bytes())
    for record in upstream:
        if digest(payloads[record["file"]]) != record["sha256"]:
            raise ValueError(f"Upstream notice was altered: {record['file']}")
    for path, sha in sdk["noticeFiles"].items():
        if digest(payloads[path]) != sha:
            raise ValueError(f"WebView2 SDK notice was altered: {path}")
    graphs, memberships = {}, {}
    for target in sorted(set(targets)):
        if target not in TARGETS:
            raise ValueError(f"Unreviewed release target: {target}")
        packages = target_graph(root, cargo, target)
        members = []
        for identity in sorted(packages):
            lock = locked[identity]
            if "source" not in lock:
                continue
            members.append(f"{identity[0]}@{identity[1]}")
            memberships.setdefault(identity, []).append(target)
        graphs[target] = {"components": members, "graph": f"graphs/{target}.txt", "edges": "normal,build; default features; includes build-time crates"}
        payloads[f"graphs/{target}.txt"] = ("\n".join(members)+"\n").encode("utf-8")
    components, sections = [], []
    aggregate_prefix = b"Rust desktop dependency notices. Unmodified upstream texts follow.\nAll listed normal/build dependencies are included conservatively; build-time crates need not be present in the executable.\n"
    aggregate_length = len(aggregate_prefix)
    mit_terms = (root/"LICENSE").read_text(encoding="utf-8").split("Permission is hereby granted",1)[1]
    payloads["MIT-terms.txt"] = ("MIT license terms. Original component attributions remain in the accompanying notices and source archives.\n\nPermission is hereby granted"+mit_terms).encode("utf-8")
    for (name, version), platforms in sorted(memberships.items()):
        lock = locked[(name,version)]
        if lock["source"] != "registry+https://github.com/rust-lang/crates.io-index":
            raise ValueError(f"Unreviewed Cargo source: {name}-{version}")
        candidates = list((cargo_home/"registry/cache").glob(f"*/{name}-{version}.crate"))
        if len(candidates) != 1:
            raise ValueError(f"Fetch one exact cached source crate first: {name}-{version}")
        archive = candidates[0]
        files = crate_contents(archive, lock["checksum"], name, version)
        native_payloads = [path for path in files if PurePosixPath(path).suffix.lower() in {".a", ".so", ".dylib", ".dll", ".lib", ".exe", ".pyd"}]
        if native_payloads and name != "webview2-com-sys" and set(native_payloads) != ARCHIVE_ONLY_ASSETS.get((name, version)):
            raise ValueError(f"Unreviewed embedded native payloads in {name}-{version}: {native_payloads}")
        package = tomllib.loads(files["Cargo.toml"].decode("utf-8"))["package"]
        license_declared = package.get("license")
        if license_declared not in CHOICES:
            raise ValueError(f"Unreviewed license for {name}-{version}: {license_declared}")
        notices = package_notices(files, package)
        record = {"name":name,"version":version,"crateSha256":lock["checksum"],"sourceUrl":f"https://static.crates.io/crates/{name}/{name}-{version}.crate",
                  "licenseDeclared":license_declared,"licenseSelected":CHOICES[license_declared],"targets":platforms,"authors":package.get("authors",[]),"notices":[]}
        if record["licenseSelected"] == "MPL-2.0":
            record["sourceArchive"] = f"sources/{name}-{version}.crate"
            payloads[record["sourceArchive"]] = archive.read_bytes()
        if (name, version) in ARCHIVE_ONLY_ASSETS:
            record["archiveOnlyNativeAssets"] = {path:digest(files[path]) for path in native_payloads}
            record["archiveOnlyNativeAssetsScope"] = "Upstream test fixtures referenced only by test modules. These binary fixtures and the crate archive are not copied into application packages."
        if not notices:
            vcs = json.loads(files[".cargo_vcs_info.json"])["git"]["sha1"]
            extra = [r for r in upstream if r["crate"] == f"{name}-{version}" and r["revision"] == vcs]
            if not extra:
                raise ValueError(f"Missing exact upstream license text: {name}-{version}")
            for entry in extra:
                notices[entry["url"]] = payloads[entry["file"]]
            record["upstreamNotices"] = extra
            if package.get("repository") == "https://github.com/madsmtm/objc2":
                notices["MIT license terms (upstream grant and SDK caveat retained above)"] = payloads["MIT-terms.txt"]
                record["sdkDerivedBindingCaveat"] = "Exact upstream LICENSE.md discusses Apple SDK-derived bindings; this inventory is not Apple SDK legal approval."
        for path, data in sorted(notices.items()):
            source_notice = f"\nUnmodified MPL-2.0 source is included at {record['sourceArchive']} (gzip tar crate archive)." if record.get("sourceArchive") else ""
            header = f"\n{'='*72}\n{name} {version} — {path}\nLicense declaration: {license_declared}; selected: {record['licenseSelected']}\nSource archive SHA-256: {lock['checksum']}{source_notice}\n{'-'*72}\n".encode("utf-8")
            record["notices"].append({"sourcePath":path,"sha256":digest(data),"aggregateOffset":aggregate_length+len(header),"byteLength":len(data)})
            section = header+data+b"\n"
            sections.append(section)
            aggregate_length += len(section)
        if name == "webview2-com-sys":
            if set(native_payloads) != set(sdk["embeddedPayloads"]):
                raise ValueError("WebView2 SDK payload inventory changed.")
            for path, sha in sdk["embeddedPayloads"].items():
                if digest(files[path]) != sha:
                    raise ValueError(f"WebView2 embedded payload differs from reviewed NuGet SDK: {path}")
        components.append(record)
    payloads["THIRD_PARTY_RUST.txt"] = aggregate_prefix+b"".join(sections)
    rust_version = subprocess.check_output([rustc,"-vV"],text=True,encoding="utf-8")
    pinned = tomllib.loads((root/"rust-toolchain.toml").read_text(encoding="utf-8"))["toolchain"]["channel"]
    if f"release: {pinned}" not in rust_version.splitlines():
        raise ValueError(f"Collect notices with the pinned Rust {pinned} toolchain.")
    sysroot = Path(subprocess.check_output([rustc,"--print","sysroot"],text=True,encoding="utf-8").strip())
    rust_docs = sysroot/"share/doc/rust"
    payloads["toolchain/COPYRIGHT-library.html"] = (rust_docs/"COPYRIGHT-library.html").read_bytes()
    for file in sorted((rust_docs/"licenses").glob("*.txt")):
        payloads[f"toolchain/licenses/{file.name}"] = file.read_bytes()
    source_inputs = {}
    for name in INPUTS:
        data = canonical_text((root/name).read_bytes())
        source_inputs[name] = digest(data)
        payloads[f"source-inputs/{name}"] = data
    manifest = {"format":"kinemeld-rust-notices/1","scope":"Cargo normal/build dependency closures for declared release targets, including build-only crates; not proof every listed crate was linked",
                "sourceInputs":source_inputs,"targets":graphs,"components":components,"toolchain":{"rustcVerbose":rust_version,"libraryNotice":"toolchain/COPYRIGHT-library.html","scope":"Rust-distributed standard-library copyright/third-party notice and accompanying license texts; compiler itself is not redistributed"},
                "webview2Sdk":sdk,"files":{name:digest(data) for name,data in sorted(payloads.items())}}
    for name, data in payloads.items():
        target = output/relative_path(name)
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(data)
    (output/"manifest.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    return check_bundle(output, source_root=root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--collect",action="store_true")
    mode.add_argument("--check",action="store_true")
    parser.add_argument("--notices",type=Path,default=ROOT/"notices/rust")
    parser.add_argument("--source-root",type=Path)
    parser.add_argument("--target",action="append",choices=TARGETS)
    parser.add_argument("--cargo",default="cargo")
    parser.add_argument("--rustc",default="rustc")
    parser.add_argument("--check-compiler",action="store_true")
    parser.add_argument("--cargo-home",type=Path,default=Path(os.environ.get("CARGO_HOME",Path.home()/".cargo")))
    args = parser.parse_args()
    if args.collect:
        result = collect(args.source_root or ROOT,args.notices,args.cargo,args.cargo_home,args.rustc,args.target or TARGETS)
    else:
        result = check_bundle(args.notices,source_root=args.source_root)
        for target in args.target or []:
            check_bundle(args.notices,target=target,source_root=args.source_root)
    if args.check_compiler:
        check_compiler(result,args.rustc)
    print(json.dumps({"ok":True,"components":len(result["components"]),"targets":{name:len(graph["components"]) for name,graph in result["targets"].items()},"files":len(result["files"])},indent=2))


if __name__ == "__main__":
    main()
