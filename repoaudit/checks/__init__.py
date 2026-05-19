"""Check registration — ALL_CHECKS is the single source of truth."""

from repoaudit.checks.ai_readiness import AIReadinessChecks
from repoaudit.checks.code_quality import CodeQualityChecks
from repoaudit.checks.devex import DevExChecks
from repoaudit.checks.security import SecurityChecks
from repoaudit.checks.service_security import ServiceSecurityChecks
from repoaudit.checks.testing import TestingChecks

ALL_CHECKS = [
    AIReadinessChecks,
    SecurityChecks,
    ServiceSecurityChecks,
    DevExChecks,
    TestingChecks,
    CodeQualityChecks,
]
