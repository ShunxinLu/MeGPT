"""
PrivacyGuard - HTML sanitization and smart PII masking.

Ported from personal_assist. Converts raw HTML emails to Markdown and masks PII.
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Try to import Presidio for PII detection, fall back to regex
try:
    from presidio_analyzer import AnalyzerEngine
    from presidio_anonymizer import AnonymizerEngine
    from presidio_anonymizer.entities import OperatorConfig
    PRESIDIO_AVAILABLE = True
except ImportError:
    PRESIDIO_AVAILABLE = False
    logger.warning("Presidio not available. Using regex-based PII masking.")

# Try to import HTML parsing libraries
try:
    from bs4 import BeautifulSoup
    from markdownify import markdownify as md
    HTML_PARSING_AVAILABLE = True
except ImportError:
    HTML_PARSING_AVAILABLE = False
    logger.warning("beautifulsoup4 or markdownify not available. Email sanitization will be limited.")


class PrivacyGuard:
    """
    In-memory HTML sanitization and PII masking.

    - Converts HTML to clean Markdown
    - Masks PII (emails, phones, SSNs, addresses) from strangers
    - Preserves family member names (whitelisted)
    """

    # Regex patterns for basic PII detection (fallback)
    PATTERNS = {
        "email": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
        "phone": re.compile(r'\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'),
        "ssn": re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
        "credit_card": re.compile(r'\b(?:\d{4}[-\s]?){3}\d{4}\b'),
    }

    # Spam/scam indicators
    SPAM_INDICATORS = [
        "you have won",
        "claim your prize",
        "nigerian prince",
        "wire transfer",
        "urgent action required",
        "verify your account immediately",
        "suspended account",
        "click here to confirm",
        "lottery winner",
        "inheritance fund",
        "bitcoin investment",
        "guaranteed return",
    ]

    def __init__(self, family_whitelist: list[str] | None = None):
        """
        Initialize PrivacyGuard.

        Args:
            family_whitelist: List of family member names to preserve (not mask)
        """
        self.family_whitelist = set(family_whitelist or [])
        self._whitelist_pattern = self._build_whitelist_pattern()

        # Initialize Presidio if available
        if PRESIDIO_AVAILABLE:
            self.analyzer = AnalyzerEngine()
            self.anonymizer = AnonymizerEngine()
            logger.info("Using Presidio for PII detection")
        else:
            self.analyzer = None
            self.anonymizer = None

    def _build_whitelist_pattern(self) -> re.Pattern | None:
        """Build regex pattern to find whitelisted names."""
        if not self.family_whitelist:
            return None
        # Escape special characters and create pattern
        escaped = [re.escape(name) for name in self.family_whitelist]
        pattern = r'\b(' + '|'.join(escaped) + r')\b'
        return re.compile(pattern, re.IGNORECASE)

    def _convert_table_to_readable(self, table) -> str:
        """
        Convert HTML table to human-readable plain text.

        Instead of markdown tables with pipes, we convert to:
        - Key-value pairs for 2-column tables
        - Bulleted lists for multi-column tables
        """
        rows = table.find_all("tr")
        if not rows:
            return ""

        result = []

        for row in rows:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue

            cell_texts = [cell.get_text(strip=True) for cell in cells]

            # For 2-column tables, use "key: value" format
            if len(cell_texts) == 2 and cell_texts[0]:
                result.append(f"{cell_texts[0]}: {cell_texts[1]}")
            # For single column, just list it
            elif len(cell_texts) == 1 and cell_texts[0]:
                result.append(f"• {cell_texts[0]}")
            # For wider tables, join with spaces or tabs
            elif len(cell_texts) > 2:
                # Use bullet for first non-empty cell, indent rest
                first_cell = next((c for c in cell_texts if c), "")
                if first_cell:
                    other_cells = [c for c in cell_texts[1:] if c]
                    result.append(f"• {first_cell} - {' | '.join(other_cells)}")

        return "\n".join(result) if result else ""

    def html_to_markdown(self, html: str) -> str:
        """
        Convert HTML email content to clean Markdown.

        Args:
            html: Raw HTML content

        Returns:
            Clean Markdown text
        """
        if not html or not isinstance(html, str):
            return ""

        if not HTML_PARSING_AVAILABLE:
            # Fallback: strip HTML tags
            html = re.sub(r'<[^>]+>', ' ', html)
            return re.sub(r'\s+', ' ', html).strip()

        try:
            # Parse with BeautifulSoup to clean up
            soup = BeautifulSoup(html, "html.parser")

            if soup is None or (soup.body is None and not soup.contents):
                # Not valid HTML, return as plain text
                return html.strip()

            # Remove script and style elements
            for element in soup(["script", "style", "head", "meta", "link"]):
                if element:
                    element.decompose()

            # Remove tracking pixels (1x1 images)
            for img in soup.find_all("img"):
                if img and hasattr(img, 'get') and hasattr(img, 'decompose'):
                    try:
                        width = img.get("width", "") or ""
                        height = img.get("height", "") or ""
                        if str(width) in ("1", "0") or str(height) in ("1", "0"):
                            img.decompose()
                    except (AttributeError, TypeError):
                        continue

            # Convert HTML tables to readable text BEFORE markdown conversion
            for table in soup.find_all("table"):
                readable_text = self._convert_table_to_readable(table)
                if readable_text:
                    # Replace table with a div containing the readable text
                    new_tag = soup.new_tag("div")
                    new_tag.string = "\n" + readable_text + "\n"
                    table.replace_with(new_tag)
                else:
                    table.decompose()

            # Convert to markdown (tables already handled)
            markdown = md(str(soup), heading_style="ATX", strip=["a"])

            if not markdown:
                # Fallback to text extraction
                return soup.get_text(separator="\n", strip=True)

            # Clean up excessive whitespace
            markdown = re.sub(r'\n{3,}', '\n\n', markdown)
            markdown = markdown.strip()

            return markdown

        except Exception as e:
            logger.error(f"HTML to Markdown conversion failed: {e}")
            # Fallback: return plain text
            try:
                soup = BeautifulSoup(html, "html.parser")
                return soup.get_text(separator="\n", strip=True)
            except Exception as e2:
                logger.error(f"Fallback text extraction also failed: {e2}")
                return html.strip() if html else ""

    def mask_pii(self, text: str) -> str:
        """
        Mask PII in text while preserving whitelisted family names.

        Args:
            text: Text to process

        Returns:
            Text with PII masked
        """
        if not text:
            return ""

        # First, protect whitelisted names by replacing with placeholders
        protected_names: dict[str, str] = {}
        if self._whitelist_pattern:
            def protect_name(match: re.Match) -> str:
                name = match.group(0)
                placeholder = f"__PROTECTED_{len(protected_names)}__"
                protected_names[placeholder] = name
                return placeholder
            text = self._whitelist_pattern.sub(protect_name, text)

        # Mask PII
        if PRESIDIO_AVAILABLE and self.analyzer and self.anonymizer:
            text = self._mask_with_presidio(text)
        else:
            text = self._mask_with_regex(text)

        # Restore protected names
        for placeholder, name in protected_names.items():
            text = text.replace(placeholder, name)

        return text

    def _mask_with_presidio(self, text: str) -> str:
        """Mask PII using Presidio analyzer."""
        try:
            # Analyze for PII entities
            results = self.analyzer.analyze(
                text=text,
                entities=["EMAIL_ADDRESS", "PHONE_NUMBER", "US_SSN", "CREDIT_CARD"],
                language="en"
            )

            if not results:
                return text

            # Anonymize detected entities
            operators = {
                "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "[EMAIL]"}),
                "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "[PHONE]"}),
                "US_SSN": OperatorConfig("replace", {"new_value": "[SSN]"}),
                "CREDIT_CARD": OperatorConfig("replace", {"new_value": "[CARD]"}),
            }

            anonymized = self.anonymizer.anonymize(
                text=text,
                analyzer_results=results,
                operators=operators
            )

            return anonymized.text

        except Exception as e:
            logger.error(f"Presidio masking failed: {e}")
            return self._mask_with_regex(text)

    def _mask_with_regex(self, text: str) -> str:
        """Mask PII using regex patterns (fallback)."""
        result = text

        replacements = {
            "email": "[EMAIL]",
            "phone": "[PHONE]",
            "ssn": "[SSN]",
            "credit_card": "[CARD]",
        }

        for pattern_name, pattern in self.PATTERNS.items():
            replacement = replacements.get(pattern_name, "[REDACTED]")
            result = pattern.sub(replacement, result)

        return result

    def strip_and_sanitize(self, raw_html: str) -> str:
        """
        Full pipeline: HTML to Markdown with PII masking.

        Args:
            raw_html: Raw HTML email content

        Returns:
            Clean, PII-masked Markdown
        """
        markdown = self.html_to_markdown(raw_html)
        masked = self.mask_pii(markdown)
        return masked

    def is_likely_spam(self, text: str, subject: str = "") -> bool:
        """
        Basic heuristic check for spam/scam indicators.

        Args:
            text: Email body text
            subject: Email subject

        Returns:
            True if likely spam/scam
        """
        combined = f"{subject} {text}".lower()

        # Check for spam patterns
        matches = sum(1 for indicator in self.SPAM_INDICATORS if indicator in combined)

        # Also check for excessive caps or special characters
        caps_ratio = sum(1 for c in combined if c.isupper()) / max(len(combined), 1)

        return matches >= 2 or caps_ratio > 0.3
