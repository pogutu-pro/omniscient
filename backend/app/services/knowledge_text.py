"""Text normalisation shared by indexing and querying.

Both sides of the match must agree exactly, so the rules live here once
rather than being reimplemented in the parser and the search service. A
mismatch is the kind of bug that does not fail loudly: the index stores
"medical" and the query looks for "medicine", every search returns nothing,
and nothing anywhere reports an error.

Everything is pure and dependency-free, which is what lets the test suite
cover the real matching behaviour without a database, a model or a network.

Deliberately not a stemmer
--------------------------
Snowball and Porter would buy more recall on queries full of morphology
("payments" / "paying" / "to pay"). They would also mangle the domain
vocabulary this corpus is made of — a stemmer happily reduces "DeKUTSO" and
"Business" and "Analysis" to forms that appear nowhere else in the
document, and every mangled term is a term that now has to be matched
through a substring test. One conservative plural rule gets almost all of
the benefit ("services" -> "service") and cannot corrupt a proper noun.
"""
from __future__ import annotations

import re

#: Words carrying no retrieval signal. Small and explicit on purpose: an
#: aggressive list throws away the question words that indicate what kind of
#: answer is wanted ("who", "when", "how"), and those are exactly the tokens
#: that separate a contact lookup from a process description.
STOPWORDS = frozenset(
    {
        "a", "am", "an", "and", "any", "are", "as", "at", "be", "been", "but", "by", "can", "could",
        "did", "do", "does", "for", "from", "get", "give", "had", "has", "have", "how", "i", "if", "in",
        "into", "is", "it", "its", "me", "might", "my", "need", "of", "on", "or", "our", "please",
        "should", "so", "some", "tell", "that", "the", "their", "them", "then", "there", "these", "they",
        "this", "to", "up", "was", "we", "were", "what", "when", "where", "which", "who", "whom", "why",
        "will", "with", "would", "you", "your",
    }
)

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
#: A hyphen between two letters joins them rather than splitting them.
#: "e-mail" is one word, and this document uses "E-MAIL" as a contact label.
#: Splitting on the hyphen yields a bare "e", which the minimum-token filter
#: below then drops, so the label indexes as "mail" while a user typing
#: "email" produces "email" — and the two can never meet. Hyphens touching a
#: digit are left as separators, because "0709-202-942" must keep its digit
#: runs distinct for the phone compactor.
_LETTER_HYPHEN = re.compile(r"(?<=[a-z])-(?=[a-z])")
_WHITESPACE = re.compile(r"\s+")
#: Seven digits is the shortest run that is unambiguously a phone number
#: rather than a year, a course code or a page reference. Kenyan mobile and
#: landline formats in this document are ten digits written "0709 202 942".
_PHONE_DIGITS = 7

#: Shortest alphabetic token worth matching. Two-letter tokens are mostly
#: noise ("de", "of", "in") and match almost any row once substring-matched
#: against an e-mail or a URL-like string.
_MIN_TOKEN = 3


def _singularise(token: str) -> str:
    """Strip a plural "s", conservatively.

    The exclusions are the words that merely end in "s": "business",
    "campus" and "analysis" are not plurals, and reducing them would leave
    a term that occurs nowhere in the document.
    """
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is", "as")):
        return token[:-1]
    return token


def _compact_digits(text: str) -> str:
    """Return the digits of `text` with separators removed, if any run is long
    enough to be a phone number.

    This is what makes "0709 202 942", "0709-202-942" and "0709202942" the
    same query. A student reading a number off a notice will type it in
    whichever of those three forms they have, and none of the word-level
    tokens they produce match each other.
    """
    runs = re.findall(r"\d+", text)
    if not runs:
        return ""
    joined = "".join(runs)
    if len(joined) >= _PHONE_DIGITS:
        return joined
    return ""


def normalise_for_search(*parts: str | None) -> str:
    """Reduce text to the normalised token string stored in `search_text`.

    Lowercased, split on every non-alphanumeric run, plural-normalised, stop
    words dropped, and — when the text contains something phone-shaped — a
    separator-free digit token appended. The result is matched by substring
    against `" " + search_text + " "`, so tokens are space-delimited to keep
    a short token from matching inside a longer one.
    """
    raw = " ".join(str(p) for p in parts if p is not None and str(p).strip())
    lowered = _LETTER_HYPHEN.sub("", raw.lower())
    tokens = [t for t in _NON_ALNUM.split(lowered) if t]
    kept = [_singularise(t) for t in tokens if len(t) >= _MIN_TOKEN and t not in STOPWORDS]
    compact = _compact_digits(lowered)
    if compact:
        kept.append(compact)
    return _WHITESPACE.sub(" ", " ".join(kept)).strip()


def tokenize(query: str) -> list[str]:
    """Turn a student's question into the tokens to match against `search_text`.

    Ordered longest-first so that a caller scoring by prefix coverage tries
    the most specific token first. Duplicates are removed: a question that
    says "fee fee payment" should not outrank one that says "fee payment"
    purely by repeating itself.
    """
    tokens = normalise_for_search(query).split()
    seen: dict[str, None] = {}
    for token in sorted(tokens, key=len, reverse=True):
        seen.setdefault(token, None)
    return list(seen)
