"""
Shared utilities for email text processing and matching.
Used by both EML/PST import and the main app UI.
"""

import re
import unicodedata


def normalize_text(value: str) -> str:
    """Normalize text by removing accents and converting to lowercase."""
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.replace("ς", "σ").lower()
    return value


def tokenize_text(value: str):
    """Tokenize text into normalized words."""
    normalized = normalize_text(value)
    normalized = re.sub(r"[^0-9a-zα-ω]+", " ", normalized)
    return [tok for tok in normalized.split() if tok]


def normalize_substation_tokens(tokens):
    """Normalize substation tokens by skipping irrelevant words and normalizing saint names."""
    normalized = []
    skip_tokens = {"υσ", "υς", "υποσταθμοσ", "υποσταθμου", "υποσταθμο"}
    for tok in tokens:
        if not tok:
            continue
        if tok in skip_tokens:
            continue
        if tok.startswith("αγι"):
            tok = "αγ"
        normalized.append(tok)
    return normalized


def tokenize_substation_text(value: str):
    """Tokenize substation text with special normalization."""
    return normalize_substation_tokens(tokenize_text(value))


def tokens_match(left_tokens, right_tokens):
    """
    Check if two token sequences match.
    
    Handles:
    - Exact matches
    - Prefix matches (e.g., "αγιος" matches "αγ" or "αζα" matches "αζας")
    - Single character changes (common in declensions)
    - Greek noun declensions (matching on first 8+ chars)
    """
    if len(left_tokens) != len(right_tokens):
        return False
    for left, right in zip(left_tokens, right_tokens):
        if left == right:
            continue
        common_len = min(len(left), len(right))
        # Allow prefix matching for short words (>=3 chars common length)
        # or longer words (>=4 chars common length)
        if common_len >= 3 and (left.startswith(right) or right.startswith(left)):
            continue
        if common_len >= 4 and left[:-1] == right[:-1]:
            continue
        # Handle Greek noun declensions by matching on the stem
        # For words >= 8 chars, match on at least the first 8 chars
        if common_len >= 8:
            if left[:8] == right[:8]:
                continue
        return False
    return True


def iter_substation_name_candidates(substation_name: str):
    """Extract all candidate names from a substation entry (main name + aliases in parentheses)."""
    if not substation_name:
        return []
    candidates = []

    def _append_candidate(value: str):
        cleaned = re.sub(r"\s+", " ", value or "").strip(" ,-")
        if cleaned and cleaned not in candidates:
            candidates.append(cleaned)

    _append_candidate(substation_name)
    _append_candidate(re.sub(r"\s*\([^)]*\)", "", substation_name))
    for alias in re.findall(r"\(([^)]+)\)", substation_name):
        _append_candidate(alias)
    return candidates
