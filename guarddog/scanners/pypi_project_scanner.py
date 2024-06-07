import logging
import re
import sys
import pkg_resources
import requests
from packaging.specifiers import Specifier

from guarddog.scanners.pypi_package_scanner import PypiPackageScanner
from guarddog.scanners.scanner import ProjectScanner
from guarddog.utils.config import VERIFY_EXHAUSTIVE_DEPENDENCIES

log = logging.getLogger("guarddog")


class PypiRequirementsScanner(ProjectScanner):
    """
    Scans all packages in the requirements.txt file of a project

    Attributes:
        package_scanner (PackageScanner): Scanner for individual packages
    """

    def __init__(self) -> None:
        super().__init__(PypiPackageScanner())

    def _sanitize_requirements(self, requirements: list[str]) -> list[str]:
        """
        Filters out non-requirement specifications from a requirements specification

        Args:
            requirements (str): PEP440 styled dependency specification text

        Returns:
            list[str]: sanitized lines containing only version specifications
        """

        sanitized_lines = []

        for line in requirements:
            is_requirement = re.match(r"\w", line)
            if is_requirement:
                if "\\" in line:
                    line = line.replace("\\", "")

                stripped_line = line.strip()
                if len(stripped_line) > 0:
                    sanitized_lines.append(stripped_line)

        return sanitized_lines

    def parse_requirements(self, raw_requirements: str) -> dict[str, set[str]]:
        """
        Parses requirements.txt specification and finds all valid
        versions of each dependency

        Args:
            raw_requirements (str): contents of requirements.txt file

        Returns:
            dict: mapping of dependencies to valid versions

            ex.
            {
                ....
                <dependency-name>: [0.0.1, 0.0.2, ...],
                ...
            }
        """
        requirements = raw_requirements.splitlines()

        def find_all_versions(package_name: str, semver_range: str) -> set[str]:
            """
            This helper function retrieves all available version of a package
            """
            url = "https://pypi.org/pypi/%s/json" % (package_name,)
            log.debug(f"Retrieving PyPI package metadata information from {url}")
            data = requests.get(url).json()
            versions = sorted(data["releases"].keys(), reverse=True)

            # Filters to specified versions
            try:
                spec = Specifier(semver_range)
                result = [m for m in spec.filter(versions)]
            except ValueError:
                # keep it raw
                result = [semver_range]

            # If just the best matched version scan is required we only keep one
            if not VERIFY_EXHAUSTIVE_DEPENDENCIES and result:
                result = [sorted(result).pop()]

            return set(result)

        sanitized_requirements = self._sanitize_requirements(requirements)

        dependencies = {}

        def safe_parse_requirements(req):
            """
            This helper function yields one valid requirement line at a time
            """
            parsed = pkg_resources.parse_requirements(req)
            while True:
                try:
                    yield next(parsed)
                except StopIteration:
                    break
                except Exception as e:
                    sys.stderr.write(
                        f"Error when parsing requirements, received error {str(e)}. This entry will be "
                        "ignored.\n"
                    )
                    yield None

        try:
            for requirement in safe_parse_requirements(sanitized_requirements):
                if requirement is None:
                    continue

                project_exists_on_pypi = True
                try:
                    versions = find_all_versions(
                        requirement.project_name,
                        (
                            requirement.url
                            if requirement.url
                            else str(requirement.specifier)
                        ),
                    )
                except Exception:
                    sys.stderr.write(
                        f"Package {requirement.project_name} not on PyPI\n"
                    )
                    project_exists_on_pypi = False
                    continue

                if project_exists_on_pypi:
                    dependencies[requirement.project_name] = versions
        except Exception as e:
            sys.stderr.write(f"Received error {str(e)}")

        return dependencies
