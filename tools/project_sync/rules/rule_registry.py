"""
Architecture Rule Registry

Stores and provides architecture validation rules.

Part of:
Project Sync Framework
Architecture Intelligence Layer
"""


from .rule_base import ArchitectureRule


class RuleRegistry:
    """
    Registry of architecture validation rules.
    """


    def __init__(self):
        self.rules: list[ArchitectureRule] = []


    def register(
        self,
        rule: ArchitectureRule,
    ) -> None:
        """
        Register architecture rule.

        Duplicate rule IDs are ignored.
        """

        if self.get_rule(rule.rule_id):
            return

        self.rules.append(rule)


    def get_rules(self) -> list[ArchitectureRule]:
        """
        Return registered rules.
        """

        return self.rules


    def get_rule(
        self,
        rule_id: str,
    ) -> ArchitectureRule | None:
        """
        Return rule by identifier.
        """

        for rule in self.rules:
            if rule.rule_id == rule_id:
                return rule

        return None


    def has_rule(
        self,
        rule_id: str,
    ) -> bool:
        """
        Check rule existence.
        """

        return self.get_rule(rule_id) is not None


    def count(self) -> int:
        """
        Return number of registered rules.
        """

        return len(self.rules)


    def get_metadata(self) -> list[dict]:
        """
        Return metadata of all rules.
        """

        return [
            rule.metadata()
            for rule in self.rules
        ]