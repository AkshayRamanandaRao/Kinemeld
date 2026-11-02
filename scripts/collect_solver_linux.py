"""Collect exact installed Debian/Ubuntu solver-library notices and source archives."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import struct
import subprocess
from urllib.parse import unquote, urlsplit, urlunsplit
import urllib.request

MIRROR_LISTS = ("/etc/apt/apt-mirrors.txt", "/etc/apt/apt-mirrors-security.txt")
UBUNTU_MIRRORS = {
    "archive.ubuntu.com": "/ubuntu", "security.ubuntu.com": "/ubuntu",
    "azure.archive.ubuntu.com": "/ubuntu", "old-releases.ubuntu.com": "/ubuntu",
    "ports.ubuntu.com": "/ubuntu-ports",
}


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            result.update(block)
    return result.hexdigest()


def reference(path):
    return {"path": str(path.resolve()), "sha256": digest(path)}


def run(*arguments):
    return subprocess.check_output(arguments, text=True, stderr=subprocess.PIPE)


def elf_identity(path):
    """Ignore patchelf layout changes while checking executable code and build identity."""
    data = path.read_bytes()
    if data[:6] != b"\x7fELF\x02\x01":
        raise ValueError(f"Expected little-endian ELF64 library: {path}")
    section_start, = struct.unpack_from("<Q", data, 40)
    section_size, section_count, names_index = struct.unpack_from("<HHH", data, 58)
    sections = [struct.unpack_from("<IIQQQQIIQQ", data, section_start + index * section_size) for index in range(section_count)]
    names = data[sections[names_index][4]:sections[names_index][4] + sections[names_index][5]]
    found = {}
    for section in sections:
        name = names[section[0]:].split(b"\0", 1)[0]
        content = data[section[4]:section[4] + section[5]]
        if name == b".text":
            found["textSha256"] = hashlib.sha256(content).hexdigest()
        elif name == b".note.gnu.build-id":
            name_size, desc_size, _ = struct.unpack_from("<III", content)
            start = 12 + (name_size + 3) // 4 * 4
            found["buildId"] = content[start:start + desc_size].hex()
    if not found.get("textSha256") or not found.get("buildId"):
        raise ValueError(f"Library lacks executable-code/build-ID evidence: {path}")
    return found


def family_for(filename):
    if re.fullmatch(r"libquadmath\.so\..+", filename):
        return "quadmath"
    if re.fullmatch(r"lib(?:gfortran|gcc_s|stdc\+\+|gomp)\.so\..+", filename):
        return "gcc-runtime"
    if re.fullmatch(r"lib(?:lapack|blas)\.so\..+", filename):
        return "lapack-blas"
    raise ValueError(f"Unreviewed Linux solver runtime: {filename}")


def installed_package(path):
    resolved = path.resolve(strict=True)
    candidates = [str(resolved), str(path)]
    for name in list(candidates):
        if name.startswith("/usr/lib/"):
            candidates.append(name.removeprefix("/usr"))
        elif name.startswith("/lib/"):
            candidates.append("/usr" + name)
    owner = None
    for name in dict.fromkeys(candidates):
        try:
            owners = run("dpkg-query", "-S", name).strip().splitlines()
        except subprocess.CalledProcessError:
            continue
        packages = {line.split(": ", 1)[0] for line in owners if ": " in line}
        if len(packages) == 1:
            owner = packages.pop()
            break
    if not owner:
        raise ValueError(f"No unique installed dpkg owner for {path}")
    template = "${binary:Package}\t${Version}\t${source:Package}\t${source:Version}\t${Architecture}\t${Status}\n"
    text = run("dpkg-query", "-W", "-f=" + template, owner)
    fields = text.strip().split("\t")
    if len(fields) != 6 or fields[5] != "install ok installed" or not all(fields[:5]):
        raise ValueError(f"Incomplete installed package identity for {path}")
    return fields[:5], text


def fields(paragraph):
    result, key = {}, None
    for line in paragraph.splitlines():
        if line.startswith((" ", "\t")) and key:
            result[key] += "\n" + line
        elif ":" in line:
            key, value = line.split(":", 1)
            result[key] = value.strip()
    return result


def read_mirror_list(name):
    path = Path(name)
    if name not in MIRROR_LISTS or path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
        raise ValueError(f"Unreviewed apt mirror-list file: {name}")
    return path.read_bytes()


def source_url(url, source_path, directory):
    """Resolve runner mirror+file transport without treating arbitrary URIs as files."""
    parsed = urlsplit(url)
    if parsed.scheme != "mirror+file":
        if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError(f"Unreviewed apt source URL: {url}")
        return urlunsplit(parsed._replace(scheme="https")), None
    if parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError(f"Unsafe apt mirror URI: {url}")
    name = next((name for name in MIRROR_LISTS if parsed.path.startswith(name + "/")), None)
    expected = PurePosixPath(source_path)
    if not name or not re.fullmatch(r"pool/(?:[A-Za-z0-9_+~.-]+/)*[A-Za-z0-9_+~.-]+", source_path) or any(part in (".", "..") for part in source_path.split("/")) or expected.is_absolute() or unquote(parsed.path[len(name) + 1:]) != source_path:
        raise ValueError(f"Apt mirror URI differs from its indexed source path: {url}")
    data = read_mirror_list(name)
    candidates = []
    for line in data.decode("utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        mirror = urlsplit(line.split()[0])
        if mirror.scheme not in ("http", "https") or mirror.hostname not in UBUNTU_MIRRORS or mirror.netloc != mirror.hostname or mirror.query or mirror.fragment:
            continue
        if mirror.path.rstrip("/") != UBUNTU_MIRRORS[mirror.hostname]:
            continue
        candidates.append(urlunsplit(mirror._replace(scheme="https", path=mirror.path.rstrip("/") + "/" + source_path)))
    if not candidates:
        raise ValueError(f"No reviewed Ubuntu HTTPS mirror in {name}")
    # Prefer the canonical archive when present; every downloaded byte still has
    # to match the exact SHA-256 from apt's source-package index.
    selected = next((value for value in candidates if urlsplit(value).hostname == "archive.ubuntu.com"), candidates[0])
    retained = directory / Path(name).name
    retained.write_bytes(data)
    return selected, {"originalUri": url, "mirrorList": name, "retainedMirrorList": reference(retained), "selectedHttpsUrl": selected}


def source_artifacts(package, version, work):
    directory = work / "apt-source" / f"{package}_{version}"
    directory.mkdir(parents=True, exist_ok=True)
    text = run("apt-cache", "showsrc", "--only-source", package)
    matches = [paragraph for paragraph in text.split("\n\n") if fields(paragraph).get("Package") == package and fields(paragraph).get("Version") == version]
    if not matches:
        raise ValueError(f"Exact source index unavailable: {package}={version}; enable matching deb-src repositories and run apt-get update.")
    paragraph = matches[0]
    metadata = fields(paragraph)
    checksums = {}
    for line in metadata.get("Checksums-Sha256", "").splitlines():
        if line.strip():
            sha, size, filename = line.split()
            if not re.fullmatch(r"[0-9a-f]{64}", sha) or Path(filename).name != filename:
                raise ValueError("Unsafe or unpinned source index entry")
            checksums[filename] = (sha, int(size))
    if not checksums:
        raise ValueError(f"Source package lacks SHA-256 index entries: {package}")
    metadata_path = directory / "apt-source-index.txt"
    metadata_path.write_text(paragraph + "\n", encoding="utf-8")
    uris = run("apt-get", "--print-uris", "source", "--download-only", f"{package}={version}")
    uris_path = directory / "apt-source-uris.txt"
    uris_path.write_text(uris, encoding="utf-8")
    records, resolutions = [], []
    for line in uris.splitlines():
        if not line.startswith("'"):
            continue
        parts = shlex.split(line)
        if len(parts) != 4 or parts[1] not in checksums:
            raise ValueError(f"Unpinned apt source URI: {line}")
        url, filename = parts[:2]
        url, resolution = source_url(url, metadata.get("Directory", "") + "/" + filename, directory)
        if resolution:
            resolutions.append(resolution)
        expected, size = checksums[filename]
        if int(parts[2]) != size:
            raise ValueError(f"Source URI/index size mismatch: {filename}")
        path = directory / filename
        if not path.exists() or digest(path) != expected:
            temporary = path.with_suffix(path.suffix + ".part")
            with urllib.request.urlopen(url, timeout=120) as response, temporary.open("wb") as handle:
                shutil.copyfileobj(response, handle)
            temporary.replace(path)
        if path.stat().st_size != size or digest(path) != expected:
            raise ValueError(f"Downloaded source checksum mismatch: {filename}")
        records.append(dict(reference(path), url=url, sourceVersion=version))
    if {Path(row["path"]).name for row in records} != set(checksums) or not any(row["path"].endswith(".dsc") for row in records):
        raise ValueError(f"Incomplete exact source package: {package}={version}")
    evidence = [reference(metadata_path), reference(uris_path)]
    if resolutions:
        resolution_path = directory / "apt-mirror-resolutions.json"
        resolution_path.write_text(json.dumps(resolutions, indent=2) + "\n", encoding="utf-8")
        evidence.append(reference(resolution_path))
        evidence.extend({item["retainedMirrorList"]["path"]: item["retainedMirrorList"] for item in resolutions}.values())
    return records, evidence


def collect(solver, work, origins):
    """Return prepare_solver_sources component specifications for all bundled Linux libraries."""
    solver, work = Path(solver), Path(work)
    work.mkdir(parents=True, exist_ok=True)
    components, source_cache = {}, {}
    for path in sorted((solver / "lib").rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(solver).as_posix()
        if path.is_symlink() or relative not in origins:
            raise ValueError(f"Missing regular-file build origin for {relative}")
        origin = Path(origins[relative])
        identity = elf_identity(path)
        if identity != elf_identity(origin):
            raise ValueError(f"Bundled library executable bytes/build-ID differ from its installed origin: {relative}")
        (package, version, source_package, source_version, architecture), package_text = installed_package(origin)
        family = family_for(path.name)
        if family == "lapack-blas" and source_package != "lapack" or family in ("quadmath", "gcc-runtime") and not re.fullmatch(r"gcc-\d+", source_package):
            raise ValueError(f"Unreviewed source package/license mapping for {relative}: {source_package}")
        name = package.replace(":", "_")
        if name not in components:
            source_key = (source_package, source_version)
            if source_key not in source_cache:
                source_cache[source_key] = source_artifacts(*source_key, work)
            sources, evidence = source_cache[source_key]
            directory = work / "installed-packages" / name
            directory.mkdir(parents=True, exist_ok=True)
            package_metadata = directory / "dpkg-package.txt"
            package_metadata.write_text(package_text, encoding="utf-8")
            notice = Path("/usr/share/doc") / package.split(":", 1)[0] / "copyright"
            if not notice.is_file():
                raise ValueError(f"Installed package copyright notice is missing: {package}")
            copy = directory / "copyright"
            shutil.copyfile(notice, copy)
            components[name] = dict(name=name, family=family, version=version, sourceVersion=source_version,
                                    files=[], packageNotice=reference(copy), sources=sources,
                                    evidence=evidence + [reference(package_metadata)])
        component = components[name]
        if (component["family"], component["version"]) != (family, version):
            raise ValueError(f"Installed package mixes unreviewed license families or versions: {package}")
        identity_path = work / "installed-packages" / name / (path.name + ".identity.json")
        identity_path.write_text(json.dumps(dict(file=relative, origin=str(origin), originSha256=digest(origin),
                                               bundledSha256=digest(path), identity=identity), indent=2) + "\n", encoding="utf-8")
        component["files"].append(relative)
        component["evidence"].append(reference(identity_path))
    return list(components.values())
