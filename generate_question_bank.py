"""
Domain-agnostic multi-word keyword extractor from a single question string.

Strategy (robust, no external config):
1) Prefer spaCy noun-phrase chunks (with NER heads) → cleaned, 2–6 token phrases.
2) If spaCy isn't available or finds little, use a RAKE-like heuristic:
   - Split on stopwords/punctuation to form candidate phrases
   - Score by degree/frequency + position bonus
3) Post-process: de-duplicate, strip generic/verb-only phrases, keep hyphens & digits.

Usage:
    from keyword_extractor import extract_keywords
    kws = extract_keywords("Briefly describe breakpoint chlorination and chlorine demand", max_keywords=3)

Requires (optional): spaCy with en_core_web_sm (auto-download attempt included).

Author: Amit project – Keyword module
"""

from __future__ import annotations
import re
from typing import List, Tuple

# --- Optional spaCy load with auto-download ---
try:
    import spacy  # type: ignore
    try:
        _NLP = spacy.load("en_core_web_sm")
    except Exception:
        try:
            from spacy.cli import download as _spacy_download
            _spacy_download("en_core_web_sm")
            _NLP = spacy.load("en_core_web_sm")
        except Exception:
            _NLP = None
except Exception:  # pragma: no cover
    _NLP = None

# --- Small, general stoplist ---
_STOP = set(
    """
    a an and are as at be been being but by can cannot could did do does doing done for from had has have having how i if in into is it its it's of on onto or our out per shall should than that the their them then there these they this those to under upon was we were what when where which who whom why will with would you your yours
    about above after again against all almost also although always among amount
    because before between both each either enough especially etc few further however
    including instead least less many more most much neither never often other otherwise
    same several some such through throughout unless until very via while within without
    define definition describe explanation explain discuss briefly write list state name give show draw calculate solve determine find compute compare analyze analyse assess evaluate identify demonstrate apply design develop construct create formulate justify argue critique outline summarize classify distinguish examine
    question answer marks unit subunit co teacher id year frequency keywords blooms taxonomy course outcome tag type
    """.split()
)

_GENERIC = {
    "introduction","overview","system","method","methods","process","processes",
    "concept","types","factors","steps","advantages","disadvantages","merits","demerits",
    "importance","role","effect","effects","impact","principles","principle","purpose",
    "function","functions","components","parameters","features","example","examples"
}

# Regex helpers
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]*")
_SPLIT = re.compile(r"[\s,;:/\\()\[\]{}<>]+")


def _strip_edge_stops(tokens: List[str]) -> List[str]:
    i, j = 0, len(tokens) - 1
    while i <= j and (tokens[i].lower() in _STOP or len(tokens[i]) <= 1):
        i += 1
    while j >= i and (tokens[j].lower() in _STOP or len(tokens[j]) <= 1):
        j -= 1
    return tokens[i:j+1]


def _clean_phrase(tokens: List[str]) -> str:
    toks = _strip_edge_stops(tokens)
    if not toks:
        return ""
    text = " ".join(toks)
    # drop too generic
    if text.lower() in _GENERIC:
        return ""
    # reject if looks like a verb directive only
    if len(toks) == 1 and toks[0].lower() in _STOP:
        return ""
    return text.lower()

# ---------------- spaCy path -----------------

def _candidates_spacy(text: str) -> List[str]:
    if not _NLP:
        return []
    doc = _NLP(text)
    cands: List[str] = []

    # 1) Noun chunks
    for chunk in doc.noun_chunks:
        toks = [t.text for t in chunk if (t.is_alpha or t.is_digit or '-' in t.text)]
        toks = _strip_edge_stops(toks)
        if 2 <= len(toks) <= 6:
            ph = _clean_phrase(toks)
            if ph:
                cands.append(ph)

    # 2) Named entities (ORG/PRODUCT/WORK_OF_ART/EVENT etc.) as phrases
    for ent in doc.ents:
        if ent.label_ in {"ORG","PRODUCT","WORK_OF_ART","EVENT","FAC","GPE","LAW"}:
            toks = [t.text for t in ent if (t.is_alpha or t.is_digit or '-' in t.text)]
            ph = _clean_phrase(toks)
            if ph:
                cands.append(ph)

    # Uniques, preserve order
    seen, result = set(), []
    for ph in cands:
        if ph not in seen:
            seen.add(ph); result.append(ph)
    return result

# --------------- Heuristic RAKE-like path ---------------

def _candidates_rake(text: str) -> List[str]:
    tokens = [t for t in _WORD.findall(text)]
    # split into chunks on stopwords
    chunks: List[List[str]] = []
    cur: List[str] = []
    for t in tokens:
        if t.lower() in _STOP:
            if cur:
                chunks.append(cur); cur = []
        else:
            cur.append(t)
    if cur:
        chunks.append(cur)

    # score by degree/frequency
    freq = {}
    deg = {}
    for ch in chunks:
        for w in ch:
            lw = w.lower()
            freq[lw] = freq.get(lw, 0) + 1
            deg[lw] = deg.get(lw, 0) + (len(ch) - 1)
    scores = {w: (deg[w] + freq[w]) / float(freq[w]) for w in freq}

    # candidate phrases 2–6 tokens with score
    cand_scored: List[Tuple[float,str]] = []
    for ch in chunks:
        if 2 <= len(ch) <= 6:
            ph = _clean_phrase([w.lower() for w in ch])
            if not ph:
                continue
            s = sum(scores.get(w.lower(), 1.0) for w in ch)
            cand_scored.append((s, ph))

    # sort by score desc then length desc
    cand_scored.sort(key=lambda x: (-x[0], -len(x[1])))

    # unique preserve order
    seen, result = set(), []
    for _, ph in cand_scored:
        if ph not in seen:
            seen.add(ph); result.append(ph)
    return result

# --------------- Public API ---------------

def extract_keywords(text: str, max_keywords: int = 3) -> List[str]:
    """Extract up to `max_keywords` multi-word keywords from a question string.
    Works for any domain. Returns lowercased phrases.
    """
    if not text or not text.strip():
        return []

    # 1) Try spaCy candidates
    phrases = _candidates_spacy(text)

    # 2) If not enough, add heuristic phrases
    if len(phrases) < max_keywords:
        extra = _candidates_rake(text)
        # merge while preserving order and uniqueness
        seen = set(phrases)
        for ph in extra:
            if ph not in seen:
                phrases.append(ph); seen.add(ph)
            if len(phrases) >= max_keywords:
                break

    # 3) If STILL empty, fallback to best bigrams from tokens
    if not phrases:
        tokens = [w.lower() for w in _WORD.findall(text) if w.lower() not in _STOP]
        for n in (3, 2):
            for i in range(0, max(0, len(tokens) - n + 1)):
                cand = " ".join(tokens[i:i+n])
                if len(cand) >= 4 and cand not in _GENERIC:
                    phrases.append(cand)
                    if len(phrases) >= max_keywords:
                        break
            if phrases:
                break

    return phrases[:max_keywords]


if __name__ == "__main__":
    tests = [
        "Define 'free available chlorine' and 'chlorine demand' in the context of water treatment.",
        "Briefly describe the concept of breakpoint chlorination.",
        "Demonstrate how reverse osmosis can be used to desalinate brackish water.",
        "Explain the working of a cyclone separator for air pollution control.",
        "What are convolutional neural networks and how are they trained?",
        "Design a reinforced concrete beam for a 6 m span with service loads.",
        "Compare IPv4 and IPv6 addressing schemes with examples.",
    ]
    for t in tests:
        print(t)
        print(" → ", extract_keywords(t))
        print()
