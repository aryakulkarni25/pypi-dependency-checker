
import json
import re
import sys
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from pathlib import Path
from email.utils import parsedate_to_datetime


PYPI_URL = "https://pypi.org/pypi"


def fetch_json(url):
    """Fetch JSON from PyPI. Return None when the resource is missing."""
    request = Request(
        url,
        headers={"User-Agent": "PyPI-Dependency-Checker/1.0"}
    )

    try:
        with urlopen(request, timeout=15) as response:
            return json.load(response)

    except HTTPError as error:
        if error.code == 404:
            return None
        raise

    except URLError as error:
        raise RuntimeError(f"Could not contact PyPI: {error}") from error


def parse_dependency(line):
    """Extract the package name and an optional pinned version."""
    line = line.strip()

    # Support common requirements-file comments and blank lines.
    if not line or line.startswith("#"):
        return None

    # Accept both == and the assignment's single = notation.
    match = re.fullmatch(
        r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*"
        r"(?:={1,2}\s*([A-Za-z0-9][A-Za-z0-9.!+_-]*))?"
        r"\s*",
        line,
    )

    if not match:
        raise ValueError(f"Unsupported requirement format: {line}")

    name = match.group(1)
    version = match.group(2)

    return name, version


def get_upload_year(release_data):
    """Get the year from the first file listed under urls."""
    urls = release_data.get("urls", [])

    if not urls:
        return None

    upload_time = urls[0].get("upload_time")
    if not upload_time:
        return None

    # PyPI normally returns an ISO-formatted timestamp.
    try:
        return datetime.fromisoformat(
            upload_time.replace("Z", "+00:00")
        ).year
    except ValueError:
        # Fallback for an RFC-formatted timestamp.
        try:
            return parsedate_to_datetime(upload_time).year
        except (TypeError, ValueError):
            return None


def main():
    filename = (
        sys.argv[1] if len(sys.argv) > 1 else "requirements.txt"
    )

    path = Path(filename)
    if not path.is_file():
        print(f"Error: File not found: {filename}", file=sys.stderr)
        sys.exit(1)

    # Each non-empty, non-comment requirement counts as a dependency.
    dependencies = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            parsed = parse_dependency(line)
            if parsed is not None:
                dependencies.append(parsed)
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)

    missing_packages = 0
    missing_versions = 0
    valid_releases = []

    for name, version in dependencies:
        package_url = f"{PYPI_URL}/{name}/json"

        try:
            package_data = fetch_json(package_url)

            if package_data is None:
                missing_packages += 1
                continue

            # An unpinned dependency only requires a package-existence check.
            if version is None:
                continue

            version_url = f"{PYPI_URL}/{name}/{version}/json"
            release_data = fetch_json(version_url)

            if release_data is None:
                missing_versions += 1
                continue

            year = get_upload_year(release_data)
            if year is not None:
                valid_releases.append((year, name, version))

        except (URLError, RuntimeError, HTTPError, TimeoutError) as error:
            print(
                f"Error checking {name}: {error}",
                file=sys.stderr
            )
            sys.exit(1)

    print(f"Dependencies checked: {len(dependencies)}")
    print(f"Packages not on PyPI: {missing_packages}")
    print(f"Versions not on PyPI: {missing_versions}")

    if valid_releases:
        year, name, version = min(valid_releases)
        print(f"Oldest pinned release: {name}=={version} ({year})")
    else:
        print("Oldest pinned release: None")


if __name__ == "__main__":
    main()
