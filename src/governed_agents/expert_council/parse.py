"""Parse structured material (proposal, paper, topic brief) into fields."""

import re

STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "from", "are", "was", "were",
    "has", "have", "had", "will", "would", "can", "could", "should", "may",
    "our", "their", "its", "into", "over", "under", "between", "through",
    "using", "used", "use", "based", "propose", "proposed", "also", "such",
    "than", "then", "them", "they", "these", "those", "which", "while",
    "where", "when", "what", "how", "all", "any", "each", "more", "most",
    "other", "some", "only", "not", "but", "out", "about", "after", "before",
}

SECTION_RE = re.compile(
    r"^(TITLE|ABSTRACT|CLAIMS|METHODS|BACKGROUND|RISKS|DATA)\s*:\s*(.*)$",
    re.IGNORECASE | re.MULTILINE,
)


def tokenize(text):
    words = re.findall(r"[a-z][a-z0-9\-/]*", text.lower())
    out = []
    for w in words:
        out.append(w)
        # also index hyphen/slash-separated parts so "fine-tuning" matches "fine tuning"
        if "-" in w or "/" in w:
            out.extend(p for p in re.split(r"[-/]", w) if len(p) > 2)
    return [w for w in out if len(w) > 2 and w not in STOPWORDS]


def parse_material(text):
    """Parse structured text with SECTION: headers into a material dict."""
    sections = {}
    matches = list(SECTION_RE.finditer(text))
    for i, m in enumerate(matches):
        name = m.group(1).upper()
        start = m.start(2)  # start of the section body (same line as the header)
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[name] = text[start:end].strip()
    body = " ".join(sections.values()) or text
    tokens = tokenize(body)
    return {
        "sections": sections,
        "title": sections.get("TITLE", ""),
        "abstract": sections.get("ABSTRACT", ""),
        "claims": sections.get("CLAIMS", ""),
        "methods": sections.get("METHODS", ""),
        "text": body,
        "tokens": tokens,
        "token_set": set(tokens),
    }
