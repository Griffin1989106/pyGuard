import os
import sys
from pathlib import Path

from semgrep.semgrep_main import invoke_semgrep

from pysecurity.analyzer.metadata.compromised_email import \
    CompromisedEmailDetector
from pysecurity.analyzer.metadata.empty_information import EmptyInfoDetector
from pysecurity.analyzer.metadata.typosquatting import TyposquatDetector


class Analyzer:
    def __init__(self) -> None:
        self.metadata_path = os.path.join(os.path.dirname(__file__), "metadata")
        self.sourcecode_path = os.path.join(os.path.dirname(__file__), "sourcecode")
        
        # Define sourcecode and metadata rulesets
        def get_rules(file_extension, path):
            return set(rule.replace(file_extension, "") for rule in os.listdir(path) if rule.endswith(file_extension))
        
        self.metadata_ruleset = get_rules(".py", self.metadata_path)
        self.sourcecode_ruleset = get_rules(".yml", self.sourcecode_path)
        
        self.metadata_ruleset.remove("detector")
        
        # Define paths to exclude from sourcecode analysis
        self.exclude = [
            "helm",
            ".idea",
            "venv",
            "test",
            "tests",
            ".env",
            "dist",
            "build",
            "semgrep",
            "migrations",
            ".github",
            ".semgrep_logs"
        ]
        
        # Rules and associated detectors
        self.metadata_detectors = {
            "typosquatting": TyposquatDetector(),
            "compromised_email": CompromisedEmailDetector(),
            "empty_information": EmptyInfoDetector()
        }
        
    
    def analyze(self, path, info=None, rules=None) -> dict[str]:
        """ Analyzes a package in the given path

        Args:
            path (str): path to package
            info (dict, optional): Any package information to analyze metadata. Defaults to None.
            rules (set, optional): Set of rules to analyze. Defaults to all rules.

        Raises:
            Exception: "{rule} is not a valid rule."

        Returns:
            dict[str]: each rule and their corresponding output
        """
        
        if rules is None:
            return self.analyze_metadata(info) | self.analyze_sourcecode(path)
        
        sourcecode_rules = set()
        metadata_rules = set()
        
        for rule in rules:
            if rule in self.sourcecode_ruleset:
                sourcecode_rules.add(rule)
            elif rule in self.metadata_ruleset:
                metadata_rules.add(rule)
            else:
                raise Exception(f"{rule} is not a valid rule.")
        
        return self.analyze_metadata(info, metadata_rules) | self.analyze_sourcecode(path, sourcecode_rules)
    
    
    def analyze_metadata(self, info, rules=None) -> dict[str]:
        all_rules = rules if rules is not None else self.metadata_ruleset
        results = {}
        
        for rule in all_rules:
            try:
                results[rule] = self.metadata_detectors[rule].detect(info)
            except Exception as e:
                sys.stderr.write("\n")
                sys.stderr.write(f"Error while analyzing {rule}: {str(e)}")
        
        return results
    

    def analyze_sourcecode(self, path, rules=None) -> dict[str]:  
        targetpath = Path(path)
        all_rules = rules if rules is not None else self.sourcecode_ruleset
        
        results = {rule: {} for rule in all_rules}
        
        if rules is None:
            response = invoke_semgrep(Path(self.sourcecode_path), [targetpath], exclude = self.exclude, no_git_ignore=True)
            return results | self._format_semgrep_response(response, targetpath=targetpath)
        
        for rule in rules:
            try:
                response = invoke_semgrep(Path(os.path.join(self.sourcecode_path, rule + ".yml")), [targetpath], exclude = self.exclude, no_git_ignore=True)
                results = results | self._format_semgrep_response(response, rule=rule, targetpath=targetpath)
            except:
                raise RuntimeError(rule + " is not an existing rule.")
        
        return results


    def _format_semgrep_response(self, response, rule=None, targetpath=None):
        results = {}
        
        for result in response["results"]:
            label = rule or result["check_id"].split(".")[-1]
            
            message = result["extra"]["lines"]
            
            line_start = result["start"]["line"]
            file = os.path.abspath(result["path"])
            
            if targetpath:
                file = os.path.relpath(file, targetpath)
                
            location = file + ":" + str(line_start)
            
            if label not in results:
                results[label] = {location: message}
            else:
                results[label][location] = message

        return results