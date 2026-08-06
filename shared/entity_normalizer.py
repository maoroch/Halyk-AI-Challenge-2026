import re


def normalize_entity_name(name: str) -> str:
    """
    Normalizes bank counterparty names to ensure robust matching across ledgers, KYC dossiers, and audit notes.
    Strips legal form suffixes (LLP, JSC, Inc, Corp, L.L.P., ТОО, АО), punctuation, and extra spaces.
    """
    if not name:
        return ""

    text = name.lower()

    # Remove dots inside acronyms (e.g., L.L.P. -> llp)
    text = re.sub(r'\b([a-z])\.\s*([a-z])\.\s*([a-z])\.\b', r'\1\2\3', text)
    text = re.sub(r'\b([a-z])\.\s*([a-z])\.\b', r'\1\2', text)

    # Remove quotes and remaining punctuation
    text = re.sub(r'[\.,\-\'"«»]', ' ', text)

    # Remove common legal suffixes and words
    legal_words = [
        r"\bllp\b", r"\bjsc\b", r"\binc\b", r"\bcorp\b", r"\bltd\b",
        r"\bco\b", r"\bgroup\b", r"\bholdings\b", r"\benterprise\b", r"\benterprises\b",
        r"\btrading\b", r"\bhouse\b", r"\bsolutions\b", r"\bpartners\b", r"\btoo\b",
        r"\bao\b", r"\bzao\b", r"\boao\b", r"\bао\b", r"\bзао\b", r"\bоао\b"
    ]

    for lw in legal_words:
        text = re.sub(lw, " ", text, flags=re.IGNORECASE)

    # Clean multiple spaces
    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_entity_match(name1: str, name2: str) -> bool:
    norm1 = normalize_entity_name(name1)
    norm2 = normalize_entity_name(name2)

    if not norm1 or not norm2:
        return False

    if norm1 == norm2:
        return True

    if len(norm1) >= 4 and len(norm2) >= 4:
        if norm1 in norm2 or norm2 in norm1:
            return True

    return False
