""" PyPI Package Malware Scanner

CLI command that scans a PyPI package version for user-specified malware flags.
Includes rules based on package registry metadata and source code analysis.
"""
import os
import sys
from typing import cast, Optional

import click
from termcolor import colored

from guarddog.analyzer.analyzer import SEMGREP_RULE_NAMES
from guarddog.analyzer.metadata import get_metadata_detectors
from guarddog.analyzer.sourcecode import SOURCECODE_RULES
from guarddog.ecosystems import ECOSYSTEM
from guarddog.reporters.sarif import report_verify_sarif
from guarddog.scanners import get_scanner
from guarddog.scanners.scanner import PackageScanner

ALL_RULES = \
    set(get_metadata_detectors(ECOSYSTEM.NPM).keys()) \
    | set(get_metadata_detectors(ECOSYSTEM.PYPI).keys()) | SEMGREP_RULE_NAMES
EXIT_CODE_ISSUES_FOUND = 1


def common_options(fn):
    fn = click.option("--exit-non-zero-on-finding", default=False, is_flag=True,
                      help="Exit with a non-zero status code if at least one issue is identified")(fn)
    fn = click.option("-r", "--rules", multiple=True, type=click.Choice(ALL_RULES, case_sensitive=False))(fn)
    fn = click.option("-x", "--exclude-rules", multiple=True, type=click.Choice(ALL_RULES, case_sensitive=False))(fn)
    fn = click.argument("target")(fn)
    return fn


def verify_options(fn):
    fn = click.option("--output-format", default=None, type=click.Choice(["json", "sarif"], case_sensitive=False))(fn)
    return fn


def scan_options(fn):
    fn = click.option("--output-format", default=None, type=click.Choice(["json"], case_sensitive=False))(fn)
    fn = click.option("-v", "--version", default=None, help="Specify a version to scan")(fn)
    return fn


@click.group
def cli():
    """
    GuardDog cli tool to detect malware in package ecosystems

    Supports PyPI and npm

    Example: guarddog pypi scan semantic-version

    Use --help for the detail of all commands and subcommands
    """
    pass


def _get_rule_pram(rules, exclude_rules):
    rule_param = None
    if len(rules) > 0:
        rule_param = rules
    if len(exclude_rules) > 0:
        rule_param = ALL_RULES - set(exclude_rules)
        if len(rules) > 0:
            print("--rules and --exclude-rules cannot be used together")
            exit(1)
    return rule_param


def _verify(path, rules, exclude_rules, output_format, exit_non_zero_on_finding, ecosystem):
    """Verify a requirements.txt file

    Args:
        path (str): path to requirements.txt file
    """
    return_value = None
    rule_param = _get_rule_pram(rules, exclude_rules)
    scanner = get_scanner(ecosystem, True)
    if scanner is None:
        sys.stderr.write(f"Command verify is not supported for ecosystem {ecosystem}")
        exit(1)
    results = scanner.scan_local(path, rule_param)
    for result in results:
        identifier = result['dependency'] if result['version'] is None \
            else f"{result['dependency']} version {result['version']}"
        if output_format is None:
            print_scan_results(result.get('result'), identifier)

    if output_format == "json":
        import json as js
        return_value = js.dumps(results)

    if output_format == "sarif":
        return_value = report_verify_sarif(path, list(ALL_RULES), results, ecosystem)

    print(return_value)
    if exit_non_zero_on_finding:
        exit_with_status_code(results)

    return return_value  # this is mostly for testing


def _scan(identifier, version, rules, exclude_rules, output_format, exit_non_zero_on_finding, ecosystem: ECOSYSTEM):
    """Scan a package

    Args:
        identifier (str): name or path to the package
        version (str): version of the package (ex. 1.0.0), defaults to most recent
        rules (str): specific rules to run, defaults to all
    """

    rule_param = _get_rule_pram(rules, exclude_rules)
    scanner = cast(Optional[PackageScanner], get_scanner(ecosystem, False))
    if scanner is None:
        sys.stderr.write(f"Command scan is not supported for ecosystem {ecosystem}")
        exit(1)
    results = {}
    if os.path.exists(identifier):
        results = scanner.scan_local(identifier, rule_param)
    else:
        try:
            results = scanner.scan_remote(identifier, version, rule_param)
        except Exception as e:
            sys.stderr.write("\n")
            sys.stderr.write(str(e))
            sys.exit()

    if output_format == "json":
        import json as js
        print(js.dumps(results))
    else:
        print_scan_results(results, identifier)

    if exit_non_zero_on_finding:
        exit_with_status_code(results)


def _list_rules(ecosystem):
    metadata_detectors = get_metadata_detectors(ecosystem)
    if len(SOURCECODE_RULES[ecosystem]) > 0:
        print("Available source code rules:")
        for rule in SOURCECODE_RULES[ecosystem]:
            print(f"\t{rule}")
    if len(metadata_detectors.keys()) > 0:
        print("Available metadata detectors:")
        for detector in metadata_detectors.keys():
            print(f"\t{detector}")


@cli.group
def npm(**kwargs):
    """ Scan a npm package or verify a npm project
    """
    pass


@cli.group
def pypi(**kwargs):
    """ Scan a PyPI package or verify a PyPI project
    """
    pass


@npm.command("scan")
@common_options
@scan_options
def scan_npm(target, version, rules, exclude_rules, output_format, exit_non_zero_on_finding):
    """ Scan a given npm package
    """
    return _scan(target, version, rules, exclude_rules, output_format, exit_non_zero_on_finding, ECOSYSTEM.NPM)


@npm.command("verify")
@common_options
@verify_options
def verify_npm(target, rules, exclude_rules, output_format, exit_non_zero_on_finding):
    """ Verify a given npm project
    """
    return _verify(target, rules, exclude_rules, output_format, exit_non_zero_on_finding, ECOSYSTEM.NPM)


@pypi.command("scan")
@common_options
@scan_options
def scan_pypi(target, version, rules, exclude_rules, output_format, exit_non_zero_on_finding):
    """ Scan a given PyPI package
    """
    return _scan(target, version, rules, exclude_rules, output_format, exit_non_zero_on_finding, ECOSYSTEM.PYPI)


@pypi.command("verify")
@common_options
@verify_options
def verify_pypi(target, rules, exclude_rules, output_format, exit_non_zero_on_finding):
    """ Verify a given Pypi project
    """
    return _verify(target, rules, exclude_rules, output_format, exit_non_zero_on_finding, ECOSYSTEM.PYPI)


@pypi.command("list-rules")
def list_rules_pypi():
    """ Print available rules for PyPI
    """
    return _list_rules(ECOSYSTEM.PYPI)


@npm.command("list-rules")
def list_rules_npm():
    """ Print available rules for npm
    """
    return _list_rules(ECOSYSTEM.NPM)


@cli.command("verify", deprecated=True)
@common_options
@verify_options
def verify(target, rules, exclude_rules, output_format, exit_non_zero_on_finding):
    return _verify(target, rules, exclude_rules, output_format, exit_non_zero_on_finding, ECOSYSTEM.PYPI)


@cli.command("scan", deprecated=True)
@common_options
@scan_options
def scan(target, version, rules, exclude_rules, output_format, exit_non_zero_on_finding):
    return _scan(target, version, rules, exclude_rules, output_format, exit_non_zero_on_finding, ECOSYSTEM.PYPI)


# Pretty prints scan results for the console
def print_scan_results(results, identifier):
    num_issues = results.get('issues')

    if num_issues == 0:
        print("Found " + colored('0 potentially malicious indicators', 'green',
                                 attrs=['bold']) + " scanning " + colored(identifier, None, attrs=['bold']))
        print()
        return

    print("Found " + colored(str(num_issues) + ' potentially malicious indicators', 'red',
                             attrs=['bold']) + " in " + colored(identifier, None, attrs=['bold']))
    print()

    results = results.get('results', [])
    for finding in results:
        description = results[finding]
        if type(description) == str:  # package metadata
            print(colored(finding, None, attrs=['bold']) + ': ' + description)
            print()
        elif type(description) == list:  # semgrep rule result:
            source_code_findings = description
            print(colored(finding, None,
                          attrs=['bold']) + ': found ' + str(len(source_code_findings)) + ' source code matches')
            for finding in source_code_findings:
                print('  * ' + finding['message']
                      + ' at ' + finding['location'] + '\n    ' + format_code_line_for_output(finding['code']))
            print()


def format_code_line_for_output(code):
    return '    ' + colored(code.strip().replace('\n', '\n    ').replace('\t', '  '), None, 'on_red', attrs=['bold'])


# Given the results, exit with the appropriate status code
def exit_with_status_code(results):
    num_issues = results.get('issues', 0)
    if num_issues > 0:
        exit(EXIT_CODE_ISSUES_FOUND)
