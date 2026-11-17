import re
from dataclasses import dataclass
from enum import Enum


class InjectionRisk(str, Enum):
    CLEAN = "clean"
    SUSPICIOUS = "suspicious"
    MALICIOUS = "malicious"


@dataclass
class ScanResult:
    risk: InjectionRisk
    detected_patterns: list[str]
    sanitized_text: str


class InjectionDefense:
    """Detects and neutralizes indirect prompt injections embedded in untrusted external text."""

    KNOWN_ATTACK_PATTERNS = [
        (r"ignore\s+(all\s+)?(previous|prior)\s+instructions", "Instruction Override"),
        (r"system\s+override", "System Override"),
        (r"you\s+are\s+now\s+(in\s+)?(developer\s+mode|dan\s+mode|jailbreak)", "Persona Hijack"),
        (r"disregard\s+(your\s+)?(safety\s+)?(rules|guidelines)", "Rule Disregard"),
        (r"send\s+(all\s+)?(api\s+keys|passwords|secrets)\s+to", "Data Exfiltration"),
        (r"curl\s+-[A-Za-z0-9]*\s+http", "Command Exfiltration"),
        (r"print\s+['\"][A-Za-z0-9_]*_KEY['\"]", "Secret Extraction"),
    ]

    @classmethod
    def scan_and_sanitize(cls, raw_text: str, source_label: str = "untrusted_web") -> ScanResult:
        """Scans for adversarial prompt injections and encapsulates content in defensive XML delimiters."""
        detected = []

        # Check regex attack signatures
        for pattern, label in cls.KNOWN_ATTACK_PATTERNS:
            if re.search(pattern, raw_text, re.IGNORECASE):
                detected.append(label)

        # Neutralize existing closing tags to prevent delimiter escape
        escaped_text = raw_text.replace("</untrusted_external_content>", "&lt;/untrusted_external_content&gt;")

        # Encapsulate in strict delimiter block
        delimited_text = (
            f"<untrusted_external_content source=\"{source_label}\">\n"
            f"{escaped_text}\n"
            f"</untrusted_external_content>"
        )

        risk = InjectionRisk.CLEAN
        if len(detected) == 1:
            risk = InjectionRisk.SUSPICIOUS
        elif len(detected) > 1:
            risk = InjectionRisk.MALICIOUS

        return ScanResult(
            risk=risk,
            detected_patterns=detected,
            sanitized_text=delimited_text,
        )
