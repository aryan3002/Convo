#!/usr/bin/env python3
"""
Multi-tenancy scoping lint check.

This script scans the codebase for common multi-tenancy violations:
1. Hardcoded shop_id constants
2. Database queries without shop_id filter
3. Direct usage of DEFAULT_SHOP_ID (except in tenancy module)

USAGE:
    python scripts/check_tenant_scoping.py
    
    # Or with verbose output
    python scripts/check_tenant_scoping.py -v

EXIT CODES:
    0 - No issues found (or only warnings)
    1 - Critical issues found

PHASE 0 STATUS:
    This script reports warnings but does NOT fail the build.
    It's meant to help identify issues for Phase 2 migration.

PHASE 2 TODO:
    - Enable strict mode (exit 1 on any warning)
    - Add to CI/CD pipeline
    - Expand patterns for new violation types
"""

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

# ────────────────────────────────────────────────────────────────
# Configuration
# ────────────────────────────────────────────────────────────────

# Root directory to scan
SCAN_ROOT = Path(__file__).parent.parent / "Backend" / "app"

# Files/directories to exclude
EXCLUDE_PATTERNS = [
    "__pycache__",
    ".pyc",
    "tenancy/",  # Tenancy module is allowed to have these patterns
    "test_",     # Test files may have hardcoded IDs
    "migrations/",  # SQL migrations are fine
]

# Patterns that indicate tenant scoping issues
BAD_PATTERNS: List[Tuple[str, str, str]] = [
    # (pattern, severity, description)
    (
        r"^[A-Z_]*SHOP_ID\s*=\s*\d+",  # Only uppercase SHOP_ID = N
        "CRITICAL",
        "Hardcoded SHOP_ID constant - should use ShopContext resolution",
    ),
    (
        r"DEFAULT_SHOP_ID\s*=\s*\d+",
        "WARNING",
        "DEFAULT_SHOP_ID constant - only allowed in tenancy/config.py",
    ),
    (
        r"shop_id\s*=\s*1[,\)\s]",  # shop_id=1 followed by comma, paren, or space
        "WARNING", 
        "Hardcoded shop_id=1 - should use ShopContext",
    ),
    (
        r"select\(Service\)(?!.*shop_id)",
        "HIGH",
        "Service query without shop_id filter - potential cross-tenant leak",
    ),
    (
        r"select\(Stylist\)(?!.*shop_id)",
        "HIGH",
        "Stylist query without shop_id filter - potential cross-tenant leak",
    ),
    (
        r"select\(Booking\)(?!.*shop_id)",
        "MEDIUM",
        "Booking query without shop_id filter - may need scoping",
    ),
    (
        r"select\(Promo\)(?!.*shop_id)",
        "HIGH",
        "Promo query without shop_id filter - potential cross-tenant leak",
    ),
    (
        r"select\(Customer\)(?!.*shop_id)",
        "MEDIUM",
        "Customer query without shop_id filter - may need scoping",
    ),
    (
        r'\"Bishops Tempe\"',
        "WARNING",
        "Hardcoded shop name - should be dynamic from shop profile",
    ),
    (
        r"get_default_shop\(",
        "INFO",
        "Usage of get_default_shop() - will need replacement in Phase 2",
    ),
]

# Patterns that are OK (suppress false positives)
IGNORE_PATTERNS = [
    r"#.*shop_id",  # Comments
    r'""".*shop_id.*"""',  # Docstrings (partial match)
    r"# TODO",  # TODO comments
    r"shop_id: int",  # Type annotations
    r"shop_id=shop_id",  # Passing through
    r"noqa:\s*tenant-scoping",  # Explicit suppression
    r"shop_id=ctx\.shop_id",  # Using context
    r"shop_id=shop\.id",  # Using shop object
    r"\.shop_id ==",  # Filter conditions (likely scoped)
]


# ────────────────────────────────────────────────────────────────
# Data Classes
# ────────────────────────────────────────────────────────────────

@dataclass
class Finding:
    """A single tenant scoping issue."""
    
    file: Path
    line_num: int
    line_text: str
    severity: str
    description: str
    
    def __str__(self):
        return f"{self.severity}: {self.file}:{self.line_num} - {self.description}\n  > {self.line_text.strip()}"


# ────────────────────────────────────────────────────────────────
# Scanning Logic
# ────────────────────────────────────────────────────────────────

def should_exclude(path: Path) -> bool:
    """Check if a path should be excluded from scanning."""
    path_str = str(path)
    return any(excl in path_str for excl in EXCLUDE_PATTERNS)


def should_ignore_line(line: str) -> bool:
    """Check if a line should be ignored (false positive suppression)."""
    return any(re.search(pattern, line, re.IGNORECASE) for pattern in IGNORE_PATTERNS)


def scan_file(file_path: Path) -> List[Finding]:
    """Scan a single file for tenant scoping issues."""
    findings = []
    
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"Warning: Could not read {file_path}: {e}", file=sys.stderr)
        return []
    
    lines = content.split("\n")
    
    for line_num, line in enumerate(lines, 1):
        # Skip if line matches ignore pattern
        if should_ignore_line(line):
            continue
        
        for pattern, severity, description in BAD_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                # For HIGH severity issues (queries), check if shop_id is in the context
                # Look at current line plus next 5 lines for multi-line statements
                if severity == "HIGH":
                    context_window = "\n".join(lines[line_num-1:line_num+5])
                    # Check if shop_id is properly scoped in the context
                    if re.search(r"\.shop_id\s*==|shop_id\s*=\s*ctx\.shop_id|shop_id\s*=\s*shop\.id", context_window):
                        continue  # Skip - this is properly scoped
                
                findings.append(Finding(
                    file=file_path,
                    line_num=line_num,
                    line_text=line,
                    severity=severity,
                    description=description,
                ))
    
    return findings


def scan_directory(root: Path) -> List[Finding]:
    """Recursively scan a directory for tenant scoping issues."""
    all_findings = []
    
    for path in root.rglob("*.py"):
        if should_exclude(path):
            continue
        
        findings = scan_file(path)
        all_findings.extend(findings)
    
    return all_findings


# ────────────────────────────────────────────────────────────────
# Reporting
# ────────────────────────────────────────────────────────────────

def print_report(findings: List[Finding], verbose: bool = False):
    """Print the findings report."""
    
    if not findings:
        print("✅ No tenant scoping issues found!")
        return
    
    # Group by severity
    by_severity = {}
    for f in findings:
        by_severity.setdefault(f.severity, []).append(f)
    
    # Print summary
    print("\n" + "=" * 60)
    print("MULTI-TENANCY SCOPING CHECK REPORT")
    print("=" * 60)
    
    severity_order = ["CRITICAL", "HIGH", "MEDIUM", "WARNING", "INFO"]
    severity_emoji = {
        "CRITICAL": "🔴",
        "HIGH": "🟠",
        "MEDIUM": "🟡",
        "WARNING": "🟣",
        "INFO": "🔵",
    }
    
    print("\nSUMMARY:")
    for sev in severity_order:
        count = len(by_severity.get(sev, []))
        if count > 0:
            print(f"  {severity_emoji.get(sev, '⚪')} {sev}: {count}")
    
    print(f"\nTOTAL: {len(findings)} issues")
    
    if verbose:
        print("\n" + "-" * 60)
        print("DETAILS:")
        print("-" * 60)
        
        for sev in severity_order:
            if sev in by_severity:
                print(f"\n{severity_emoji.get(sev, '⚪')} {sev}:")
                for f in by_severity[sev]:
                    print(f"  {f.file}:{f.line_num}")
                    print(f"    {f.description}")
                    print(f"    > {f.line_text.strip()[:80]}")
    else:
        print("\nRun with -v for detailed findings.")
    
    print("\n" + "=" * 60)
    print("NOTE: This is a Phase 0 check. These are expected findings.")
    print("Phase 2 will address these issues systematically.")
    print("=" * 60)


# ────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Check codebase for multi-tenancy scoping issues"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show detailed findings"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if any issues found (for CI)"
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=SCAN_ROOT,
        help=f"Path to scan (default: {SCAN_ROOT})"
    )
    
    args = parser.parse_args()
    
    if not args.path.exists():
        print(f"Error: Path {args.path} does not exist", file=sys.stderr)
        sys.exit(1)
    
    print(f"Scanning {args.path}...")
    findings = scan_directory(args.path)
    
    print_report(findings, verbose=args.verbose)
    
    # Exit code
    if args.strict and findings:
        critical_count = sum(1 for f in findings if f.severity in ("CRITICAL", "HIGH"))
        if critical_count > 0:
            print(f"\n❌ {critical_count} critical/high issues found. Failing.")
            sys.exit(1)
    
    sys.exit(0)


if __name__ == "__main__":
    main()
