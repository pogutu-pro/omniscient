"""Turning the knowledge-base PDF into sections, facts and guardrails.

Pure by design: no database, no network, no model, no filesystem beyond the
bytes handed in. That is what makes the extraction testable on its own, and
it is what lets `import-timetable`-style dry runs report exactly what would
be written before anything is written.

Why parse at all, rather than store the PDF
-------------------------------------------
Storing the file and chunking it would be less code, and it would be worse
at the job. Almost every question this corpus exists to answer is an exact
lookup of a short value: an office telephone number, a Dean's e-mail, the
name of the Treasurer, whether a service is free. Extracted once, those are
indexed columns, so the answer is a btree lookup. Left as prose they are
words in a paragraph, and the only way to find them is to rank paragraphs
against an embedding - which is the expensive path this corpus does not
justify (see `app/models/knowledge.py`).

The document is not machine-generated, so this is pattern matching against
the grammar it actually uses, and it is written to be *honest* when the
grammar does not fit: anything ambiguous becomes a warning naming the line,
never a guess. A silently mis-parsed phone number is worse than a missing
one, because the missing one is visible and the wrong one is quoted back to
a student as fact.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

# --- Heading grammar -------------------------------------------------------

#: A section number: "1" or "13.1". Anchored to column 0, which is what
#: separates a real heading from an indented list item — the document uses
#: indentation consistently for its enumerations, and relying on that is
#: safer than trying to tell a heading from a list item by its wording.
_HEADING = re.compile(r"^(\d+(?:\.\d+)*)\.?[ \t]+(\S.*)$")

#: A heading wrapped onto its own line by the PDF's page width, e.g.
#: "2. SCHOOLS AND CONTACT" / "INFORMATION". Only ever consumed directly
#: after a heading, so a standalone all-caps line in body text (a role
#: title such as "Chairperson") is never swallowed by accident.
_UPPER = re.compile(r"^[A-Z0-9][A-Z0-9 '’/&()–—-]*[A-Z0-9)]$")
_HAS_LETTER = re.compile(r"[A-Za-z]")

#: A heading is short. A long line that happens to start with a number is
#: body text — "2026/2027 joining instructions require..." begins with a
#: number but is not followed by whitespace, and the length cap catches the
#: rest.
_MAX_HEADING_CHARS = 80

# --- Item grammar ----------------------------------------------------------

_BULLET = re.compile(r"^[ \t]*(?:•|●|[-*])[ \t]+(\S.*)$")
_ENUMERATED = re.compile(r"^[ \t]+(\d+)\.[ \t]+(\S.*)$")
# A label may contain spaces ("Dean's office email", "Faculty telephone"),
# so the class includes one, and the word count is capped instead: without
# that cap a prose sentence carrying a colon reads as a label.
_LABEL_VALUE = re.compile(r"^[ \t]*(?:•[ \t]*)?([A-Z][A-Za-z'’/&()\-]*(?:[ \t][A-Za-z'’/&()\-.]+){0,4})[ \t]*:[ \t]*(\S.*)$")
# The contact directory puts the label on its own line and the value under
# it, so the "no value" case needs its own pattern rather than a special
# case in the one above.
_LABEL_ONLY = re.compile(r"^[ \t]*(?:•[ \t]*)?([A-Z][A-Za-z'’/&()\-]*(?:[ \t][A-Za-z'’/&()\-.]+){0,4})[ \t]*:[ \t]*$")
_STEP = re.compile(r"^(?:Step|STEP)[ \t]+(\d+)[ \t]*[—–-][ \t]*(\S.*)$")
_RULE = re.compile(r"^Rule[ \t]+(\d+)[ \t]*[—–-][ \t]*(\S.*)$")
_ATTRIBUTED = re.compile(r"^Data[ \t]+Assembled[ \t]+by,?[ \t:]*(\S.*)$", re.IGNORECASE)

#: A `label: value` line is a short administrative line. This document does
#: use colons inside prose, and the decisive difference is length: a table
#: row is terse, a sentence that happens to contain a colon is not.
_MAX_LABEL_LINE = 160
#: A bare term used as a mini-heading, immediately above its explanation
#: ("Consultation" / "Free for students on production of valid identification"). Capped
#: so a wrapped prose line cannot qualify.
_MAX_DEFINITION_TERM = 70
_MIN_DEFINITION_DETAIL = 30
#: An entity name is a name, not a sentence. This document puts plenty of
#: prose directly above an administrative label, and a 90-character entity
#: built out of a wrapped sentence is not a fact about anything.
_MAX_ENTITY_CHARS = 60

#: Labels whose value this importer is expected to recover exactly. Only
#: these produce a warning when their value cannot be read, because they are
#: the only ones where a wrong answer is a wrong phone number or e-mail
#: address quoted back to a student as fact. Ordinary prose that happens to
#: end in a colon ("These include:") is not a failed lookup and must not
#: report itself as one.
_CONTACT_FIELD_LABELS = frozenset(
    {
        "telephone", "phone", "tel", "mobile", "email", "e-mail", "contact",
        "address", "physical address", "postal address", "p.o. box", "po box",
    }
)

#: Values that are unambiguous enough to pair with a label sitting alone on
#: its own line, which is how the contact directory lays them out:
#:
#:     Telephone:
#:     0743 150 434
#:
#: Only these two shapes qualify. Pairing a bare label with whatever prose
#: happens to follow is how a parser ends up asserting that
#: "medicalofficer@dkut.ac.ke" is the Dean's telephone number.
_PHONE = re.compile(r"^\+?\d[\d\s()-]{6,}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PERSON_NAME = re.compile(r"^[A-Z][A-Za-z'’-]+(?:[ \t]+[A-Z][A-Za-z'’-]+){1,3}$")

#: The seven elected offices of the DeKUTSO Students' Council, as
#: enumerated in the document itself. Section 13 lists the office holder
#: under the office title with nothing else to distinguish them, so
#: recognising the titles needs a vocabulary; taking it from the document
#: rather than from guesswork is what keeps the pairing exact.
DEKUTSO_OFFICES: tuple[str, ...] = (
    "Chairperson",
    "Vice Chairperson",
    "Secretary General",
    "Gender and Disability Mainstreaming Secretary",
    "Sports, Entertainment and Security Secretary",
    "Treasurer",
    "Campuses' Secretary",
)

#: Coarse categories, inferred from keywords in the enclosing section
#: title. Deliberately a short, inspectable list: `category` exists so a
#: caller can scope a query ("only medical services"), not so it can carry
#: meaning the document does not state.
_CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("school", ("school", "faculty")),
    ("institute", ("institute",)),
    ("committee", ("committee",)),
    ("leadership", ("leadership", "leadership structure", "electoral", "constitution", "current leaders")),
    ("medical", ("medical", "health", "ambulance", "dental", "referral", "sha")),
    ("fee_payment", ("fee payment", "payment", "financial", "finance", "bursary")),
    ("registration", ("registration", "admission", "new student", "self-sponsored")),
    ("portal", ("portal",)),
    ("support_routing", ("support structure", "handle academic", "student journey", "escalat")),
    ("contact", ("contact", "directory", "contact information")),
)

_GENERAL = "general"

#: The institution the document describes, used as the entity for the
#: front-matter profile lines ("Institution:", "Abbreviation:", ...).
_DEFAULT_ENTITY = "DeKUT"


class KnowledgeParseError(RuntimeError):
    """Raised when the input cannot be read as a knowledge document at all."""


@dataclass(frozen=True)
class ParsedSection:
    number: str
    title: str
    body: str


@dataclass(frozen=True)
class ParsedFact:
    section_number: str
    category: str
    entity: str
    attribute: str
    value: str
    detail: str = ""
    ordinal: int = 0
    #: The prose that introduces a list, when there is one ("Expenditure can
    #: include:"). Never stored. It exists so that two lists in the same
    #: section — which both start again at ordinal 1 — can be told apart;
    #: see `_disambiguate`.
    list_label: str = ""


@dataclass(frozen=True)
class ParsedGuardrail:
    rule_number: int
    title: str
    body: str


@dataclass(frozen=True)
class ParsedDocument:
    title: str
    sections: list[ParsedSection] = field(default_factory=list)
    facts: list[ParsedFact] = field(default_factory=list)
    guardrails: list[ParsedGuardrail] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def slugify_attribute(label: str) -> str:
    """Normalise a document label into a stable column value.

    "Dean's office email" and "Deans' office e-mail" must produce the same
    attribute, or a revised document would land as a second contact row for
    the same person instead of updating the first.
    """
    text = label.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    # Fold the British/American spelling differences the document itself
    # mixes ("e-mail" and "email") without a general stemmer.
    text = re.sub(r"^e_?mail$", "email", text)
    return text or "item"


def _is_heading(line: str) -> re.Match[str] | None:
    if not line or line[0].isspace():
        return None
    match = _HEADING.match(line)
    if not match or len(match.group(2)) > _MAX_HEADING_CHARS:
        return None
    number, rest = match.group(1), match.group(2).strip()
    # A heading contains letters. Without this, a telephone number sitting in
    # the left margin is read as a heading: "0709 202 942" matches the
    # numbering pattern, and because digits are unchanged by `.upper()` it
    # also passes the capitals test, so the directory's contact numbers were
    # being indexed as sections numbered 709 and 743.
    if not _HAS_LETTER.search(rest):
        return None
    # A heading is a title, not a sentence: it is set in capitals, or it is a
    # numbered subsection in title case. "2.1 Official Schools" qualifies on
    # the second clause; a wrapped body line that happens to start with a
    # number does not.
    if number.count(".") == 0:
        return match if rest == rest.upper() else None
    return match


def _looks_like_value(text: str) -> bool:
    return bool(_PHONE.match(text) or _EMAIL.match(text))


@dataclass
class _Line:
    text: str
    section_number: str
    section_title: str
    context: str


def _categorise(section_title: str, context: str) -> str:
    haystack = f"{section_title} {context}".lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            return category
    return _GENERAL


def _join_paragraphs(lines: list[str]) -> str:
    return "\n".join(part for part in lines if part).strip()


def parse_knowledge_document(text: str, *, source_name: str = "") -> ParsedDocument:
    """Parse knowledge-base text into sections, facts and guardrails.

    The same text always yields the same result: no clock, no randomness and
    no network. That is a precondition for the idempotent re-ingest in
    `app.services.knowledge_ingest` — if parsing were unstable, a re-run
    would insert duplicates instead of updating rows.
    """
    if not text or not text.strip():
        raise KnowledgeParseError(f"{source_name or 'Document'} contains no text to parse.")

    # A form feed is a page break, not content. Extractors disagree about
    # whether to emit one: pypdf does not, but `pdftotext` puts \f in front
    # of the first line of every page. Left in place it makes that line
    # start with whitespace, which fails the "headings start at column 0"
    # test, and every heading that happens to start a page is silently lost
    # from the knowledge base. Turning it into a newline fixes the cause
    # rather than loosening the test. It is a targeted replacement rather
    # than a blanket `strip()`, because the leading whitespace on an
    # indented list item is load-bearing throughout this module.
    raw_lines = [
        line.rstrip()
        for line in text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n").replace("\v", "\n").split("\n")
    ]
    lines = [line for line in raw_lines if line.strip()]

    headings: list[tuple[int, int, str, str]] = []  # (heading line, first body line, number, title)
    index = 0
    while index < len(lines):
        match = _is_heading(lines[index])
        if match is None:
            index += 1
            continue
        title = match.group(2).strip()
        # The heading's own line, kept separate from the cursor: absorbing a
        # wrapped continuation advances the cursor past lines that still
        # belong to this heading's title, and recording the advanced position
        # would slice the following section's body into the wrong section.
        start = index
        # Absorb wrapped continuation lines. A heading set in capitals is
        # continued by further capitals and stops at the first line that is
        # not: that is the only signal available, and it holds because body
        # text in this document is sentence case throughout.
        if title == title.upper():
            while index + 1 < len(lines) and not _is_heading(lines[index + 1]):
                candidate = lines[index + 1].strip()
                if not candidate or candidate != candidate.upper() or len(candidate) > _MAX_HEADING_CHARS:
                    break
                title = f"{title} {candidate}".strip()
                index += 1
        # Body starts after every line the title consumed, so a wrapped
        # heading is not also echoed into its own section body.
        headings.append((start, index + 1, match.group(1), title))
        index += 1

    if not headings:
        raise KnowledgeParseError(
            f"{source_name or 'Document'} has no numbered sections. The importer expects a "
            "knowledge document whose headings are numbered ('1. TITLE', '1.1 Subtitle')."
        )

    warnings: list[str] = []
    doc_title = _front_matter_title(lines, headings[0][0])

    # Assign every line to its enclosing section and subsection, so each
    # extracted fact can say what it is a fact *about*.
    first_heading_index = headings[0][0]
    tagged: list[_Line] = []
    bounds = [body_start for _, body_start, _, _ in headings] + [len(lines)]
    for order, (position, body_start, number, title) in enumerate(headings):
        for line in lines[body_start : bounds[order + 1]]:
            tagged.append(_Line(text=line, section_number=number, section_title=title, context=""))
        # Anything between this heading and the next one that is itself
        # numbered is a subsection; it becomes the context for the lines
        # that follow.
        for line in tagged:
            if line.section_number == number and not line.context:
                subsection = _subsection_of(line.text)
                if subsection:
                    line.context = subsection

    sections: list[ParsedSection] = []
    for _, _, number, title in headings:
        body_lines = [line.text.strip() for line in tagged if line.section_number == number]
        sections.append(
            ParsedSection(
                number=number,
                title=title,
                body="\n".join(body for body in body_lines if body).strip(),
            )
        )

    _check_numbering(sections, warnings)

    facts: list[ParsedFact] = []
    guardrails: list[ParsedGuardrail] = []

    # Front matter: the institution profile, which sits before section 1 and
    # has no section number to cite. It is genuinely useful ("what type of
    # university is DeKUT") so it is kept, attributed to the institution.
    for line in lines[:first_heading_index]:
        fact = _label_value_fact(line.strip(), "", doc_title, _DEFAULT_ENTITY, "institution_profile")
        if fact is not None:
            facts.append(fact)
    facts.extend(_attribution_facts(lines, doc_title))

    facts = _disambiguate(_extract_facts(tagged, warnings), warnings)
    guardrails.extend(_extract_guardrails(tagged, warnings))

    return ParsedDocument(
        title=doc_title,
        sections=sections,
        facts=facts,
        guardrails=guardrails,
        warnings=warnings,
    )


def _front_matter_title(lines: list[str], first_heading_index: int) -> str:
    """Title of the document, from the first block of text before section 1."""
    block: list[str] = []
    for line in lines[:first_heading_index]:
        stripped = line.strip()
        if not stripped:
            if block:
                break
            continue
        # The profile lines that follow the title are "Label: value", not
        # part of the name.
        if _LABEL_VALUE.match(stripped):
            break
        block.append(stripped)
    return " ".join(block).strip() or "Knowledge base"


def _subsection_of(line: str) -> str | None:
    """Return the section number of a subsection heading, if this line is one."""
    stripped = line.strip()
    match = _HEADING.match(stripped)
    if not match or match.group(1).count(".") == 0:
        return None
    return match.group(1)


def _check_numbering(sections: list[ParsedSection], warnings: list[str]) -> None:
    top_level = [int(s.number) for s in sections if "." not in s.number]
    for previous, current in zip(top_level, top_level[1:]):
        if current != previous + 1:
            warnings.append(
                f"Top-level section numbering jumps from {previous} to {current}; "
                "a section may be missing from the source document."
            )
    seen: set[str] = set()
    for section in sections:
        if section.number in seen:
            warnings.append(f"Section {section.number} appears more than once; the later one was kept.")
        seen.add(section.number)


def _label_value_fact(
    line: str,
    section_number: str,
    section_title: str,
    entity: str,
    category: str,
) -> ParsedFact | None:
    match = _LABEL_VALUE.match(line)
    if not match or len(line) > _MAX_LABEL_LINE:
        return None
    label, value = match.group(1).strip(), match.group(2).strip()
    if not value:
        return None
    return ParsedFact(
        section_number=section_number,
        category=category,
        entity=entity,
        attribute=slugify_attribute(label),
        value=value,
        detail=f"{label}: {value}",
    )


#: Lowercase words that give a "Label:" line away as a sentence rather than
#: a field name. The contact directory writes "Telephone:" on its own line
#: and the value beneath it; body prose writes "Expenditure can include:"
#: and a list beneath it. Both end in a colon and both are followed by
#: something, so the only way to tell them apart is the grammar — and a
#: sentence carries a function word where a field name carries none.
_SENTENCE_WORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at,", "be", "by", "can", "for", "from", "generally", "in", "include",
        "includes", "including", "is", "it", "lists", "of", "on", "or", "provides", "such", "than", "that",
        "the", "to", "was", "were", "which", "with", "would",
    }
)


def _is_sentence_label(text: str) -> bool:
    """True for a "…:" line that is a clause introducing a list, not a
    field name waiting for its value."""
    body = text.strip().rstrip(":").lower()
    words = re.split(r"[^a-z0-9']+", body)
    return any(word in _SENTENCE_WORDS for word in words)


def _is_structural(text: str) -> bool:
    """True for a line that cannot serve as an entity name or a definition
    term: a label, a list item, a step, a rule, or a heading."""
    if _LABEL_VALUE.match(text) or _BULLET.match(text) or _ENUMERATED.match(text):
        return True
    if _STEP.match(text) or _RULE.match(text) or _is_heading(text):
        return True
    # A bare "Label:" is structural only when it reads like a field name.
    # "Expenditure can include:" is not one, and treating it as a label
    # makes the list beneath it adopt the *previous* list's introducer,
    # which then merges DeKUTSO's income and expenditure into one list.
    return bool(_LABEL_ONLY.match(text)) and not _is_sentence_label(text)


def _entity_before(tagged: list[_Line], index: int) -> str | None:
    """Name the entity that the label at `index` belongs to.

    The contact directory names its subject on the line above the label:

        Registrar, Academic Affairs and Research
        Telephone:
        0709 202 914

    so the entity is the nearest preceding line that is not itself a label,
    list item, step, rule or value.

    Three exclusions are load-bearing, and each of them was a wrong answer
    before it was a rule:

    - It never crosses a section boundary. Otherwise the first label of a
      school section, having nothing above it in its own section, reaches
      back into the previous one and files the School of Science's contacts
      under whatever prose happened to end the section before it.
    - It skips anything that is itself a value, so the `Email:` below a
      resolved `Telephone:` reuses the directory entry's name rather than
      the phone number sitting between them.
    - It rejects sentences, so a wrapped line of prose above an inline label
      does not become a 90-character "entity".
    """
    line = tagged[index]
    cursor = index - 1
    while cursor >= 0:
        if tagged[cursor].section_number != line.section_number:
            return None
        text = tagged[cursor].text.strip()
        if (
            text
            and not _is_structural(text)
            and not _looks_like_value(text)
            and len(text) <= _MAX_ENTITY_CHARS
            and not text.endswith(".")
        ):
            return text
        cursor -= 1
    return None


def _definition_fact(tagged: list[_Line], index: int) -> tuple[ParsedFact, int] | None:
    """Absorb a bare term followed by its explanation.

    Two shapes in the document are written this way and both are worth a
    row: the Medical Centre's service targets ("Consultation" / "Free for
    students on production of valid identification") and the routing table in
    the support-structure section ("Academic Issue" / "Student → Department
    → School/Institute → ...").

    The term becomes the fact's *entity*, not its value. That is what keeps
    seven consecutive definitions in one section from claiming the same
    identity: section 15 defines all seven offices' remits one after another,
    and keyed on the enclosing section they would collapse to a single row.

    Every structural test below runs against the raw line, indentation
    included. Indentation is the only signal separating an enumerated list
    item ("    1. Academics, ICT and Library Facilities") from a genuine
    term, and stripping it first turns every numbered item in the document
    into a definition.
    """
    line = tagged[index]
    if _is_structural(line.text):
        return None
    term = line.text.strip()
    if len(term) > _MAX_DEFINITION_TERM or term.endswith(".") or len(term.split()) > 8:
        return None
    following = _next_meaningful(tagged, index)
    if following is None or following.section_number != line.section_number:
        return None
    if _is_structural(following.text):
        return None
    detail = following.text.strip()
    if len(detail) < _MIN_DEFINITION_DETAIL:
        return None
    return (
        ParsedFact(
            section_number=line.section_number,
            category=_categorise(line.section_title, line.context),
            entity=term,
            attribute="description",
            value=term,
            detail=detail,
        ),
        index + 2,
    )


def _attribution_facts(lines: list[str], doc_title: str) -> list[ParsedFact]:
    facts: list[ParsedFact] = []
    for line in lines:
        match = _ATTRIBUTED.match(line.strip())
        if match:
            facts.append(
                ParsedFact(
                    section_number="",
                    category="attribution",
                    entity=doc_title,
                    attribute="assembled_by",
                    value=match.group(1).strip(),
                )
            )
    return facts


def _extract_facts(tagged: list[_Line], warnings: list[str]) -> list[ParsedFact]:
    facts: list[ParsedFact] = []
    # The nearest term acting as a heading for the lines that follow it.
    # Section 15 writes each office's responsibilities as a bare office title,
    # a sentence about it, and then a bullet list — seven lists in a row
    # under one section. Without this, all seven are filed under the section
    # title with ordinals 1..8 and the unique constraint silently keeps
    # eight of the fifty-six.
    local_context: str | None = None
    local_section: str | None = None
    index = 0
    while index < len(tagged):
        line = tagged[index]
        text = line.text.strip()
        if line.section_number != local_section:
            # A term only governs the lines beneath it, never the next
            # section. Without this reset, the last committee name in
            # section 17 becomes the entity for the list of people who may
            # use the Medical Centre in section 21.
            local_context = None
            local_section = line.section_number

        guard = _RULE.match(text)
        if guard:
            index += 1
            continue

        step = _STEP.match(text)
        if step:
            number = int(step.group(1))
            title = step.group(2).strip()
            detail_lines: list[str] = []
            cursor = index + 1
            while cursor < len(tagged) and tagged[cursor].section_number == line.section_number:
                following = tagged[cursor].text.strip()
                if _STEP.match(following) or _RULE.match(following) or _is_heading(following):
                    break
                if _BULLET.match(following) or _ENUMERATED.match(following):
                    break
                detail_lines.append(following)
                cursor += 1
            if number < 1:
                warnings.append(f"Step {number} in section {line.section_number} is not numbered from 1.")
            facts.append(
                ParsedFact(
                    section_number=line.section_number,
                    category="process_step",
                    entity=local_context or line.context or line.section_title,
                    attribute="step",
                    value=title,
                    detail=_join_paragraphs(detail_lines),
                    ordinal=number,
                )
            )
            index = cursor
            continue

        # A label with the value on the following line. Only phone numbers
        # and e-mail addresses are paired, because only those are
        # unambiguous. A label introducing a group ("Official contact:" above
        # a list of bullets) is skipped silently; anything else is reported
        # rather than guessed at.
        dangling = _LABEL_ONLY.match(text)
        if dangling:
            label_text = dangling.group(1).strip()
            following = _next_meaningful(tagged, index)
            if following is not None and following.section_number == line.section_number:
                following_text = following.text.strip()
                if _looks_like_value(following_text):
                    entity = _entity_before(tagged, index) or line.context or line.section_title
                    paired_value = _label_value_fact(
                        f"{label_text}: {following_text}",
                        following.section_number,
                        following.section_title,
                        entity,
                        "contact",
                    )
                    if paired_value is not None:
                        facts.append(paired_value)
                        local_context = None
                        index += 2
                        continue
                elif slugify_attribute(label_text) in _CONTACT_FIELD_LABELS and not _is_structural(following_text):
                    # A contact field whose value could not be read. This is
                    # the one case where guessing would be actively harmful,
                    # so it is reported rather than dropped.
                    warnings.append(
                        f"Section {line.section_number}: {label_text!r} is followed by text that is "
                        "neither a phone number nor an e-mail; no contact was recorded."
                    )

        paired = _label_value_fact(
            text,
            line.section_number,
            line.section_title,
            # A school section's contacts belong to the school, but the
            # directory's belong to the line above the label.
            _entity_before(tagged, index) or line.context or line.section_title,
            "contact",
        )
        if paired is not None:
            facts.append(paired)
            local_context = None
            index += 1
            continue

        leader = _dekutso_leader_fact(tagged, index)
        if leader is not None:
            facts.extend(leader)
            local_context = None
            index += 2
            continue

        definition = _definition_fact(tagged, index)
        if definition is not None:
            fact, index = definition
            facts.append(fact)
            # Everything up to the next term belongs to this one.
            local_context = fact.value
            continue

        item = _list_item_fact(tagged, index, warnings, local_context)
        if item is not None:
            facts.extend(item[0])
            index = item[1]
            continue

        index += 1
    return facts


def _next_meaningful(tagged: list[_Line], index: int) -> _Line | None:
    cursor = index + 1
    while cursor < len(tagged) and not tagged[cursor].text.strip():
        cursor += 1
    return tagged[cursor] if cursor < len(tagged) else None


def _dekutso_leader_fact(tagged: list[_Line], index: int) -> list[ParsedFact] | None:
    """Pair an office title with the office holder's name on the next line.

    Requires both the title to be one the document itself enumerates and the
    following line to look like a person's name, so a role title followed by
    a sentence of prose ("Chairperson" / "The Chairperson is responsible
    for...") produces nothing rather than a nonsense fact.
    """
    title = tagged[index].text.strip()
    if title not in DEKUTSO_OFFICES:
        return None
    following = _next_meaningful(tagged, index)
    if following is None or not _PERSON_NAME.match(following.text.strip()):
        return None
    name = following.text.strip()
    return [
        ParsedFact(
            section_number=tagged[index].section_number,
            category="leadership",
            entity="DeKUTSO",
            attribute=slugify_attribute(title),
            value=name,
            detail=f"{title} of the DeKUTSO Students' Council",
        )
    ]


def _list_item_fact(
    tagged: list[_Line], index: int, warnings: list[str], local_context: str | None = None
) -> tuple[list[ParsedFact], int] | None:
    """Absorb a run of bullets or an indented enumeration into ordered facts.

    Ordinals come from the document's own numbering when it has one, and
    from the position within the run when it does not, so the order the
    source states is the order that survives into the database. `local_context`
    is the term governing the run, so two lists under different terms in the
    same section do not claim the same ordinals.
    """
    first = tagged[index]
    bullet = _BULLET.match(first.text)
    enumerated = _ENUMERATED.match(first.text)
    if not bullet and not enumerated:
        return None

    category = _categorise(first.section_title, first.context)
    entity = local_context or first.context or first.section_title
    list_label = _list_introducer(tagged, index)
    facts: list[ParsedFact] = []
    position = 0
    cursor = index
    while cursor < len(tagged) and tagged[cursor].section_number == first.section_number:
        line = tagged[cursor]
        bullet_match = _BULLET.match(line.text)
        enumerated_match = _ENUMERATED.match(line.text)
        if not bullet_match and not enumerated_match:
            break
        # A bullet captures only its text; an enumeration captures the
        # number first, so the text is group 2 there and group 1 here.
        text = (bullet_match.group(1) if bullet_match else enumerated_match.group(2)).strip()
        if not text:
            warnings.append(f"Section {line.section_number}: an empty list item was skipped.")
            cursor += 1
            continue
        position += 1
        ordinal = int(enumerated_match.group(1)) if (enumerated and enumerated_match) else position
        facts.append(
            ParsedFact(
                section_number=line.section_number,
                category=category,
                entity=entity,
                attribute="item",
                value=text,
                ordinal=ordinal,
                list_label=list_label,
            )
        )
        cursor += 1
    return facts, cursor


def _list_introducer(tagged: list[_Line], index: int) -> str:
    """The prose line that introduces the list starting at `index`.

    Section 18 lists DeKUTSO's income and then its expenditure, each
    restarting at "1."; section 5 lists the portal's features and then the
    fields its payment form asks for. Both pairs share a section, a context
    and an attribute, so without the introducer the second list of each pair
    would overwrite the first.
    """
    cursor = index - 1
    while cursor >= 0:
        if tagged[cursor].section_number != tagged[index].section_number:
            return ""
        text = tagged[cursor].text.strip()
        if not text or _is_structural(tagged[cursor].text):
            cursor -= 1
            continue
        if text.endswith(":"):
            return text[:-1].strip()[:80]
        return ""
    return ""


def _disambiguate(facts: list[ParsedFact], warnings: list[str]) -> list[ParsedFact]:
    """Separate facts that would otherwise claim the same identity.

    `knowledge_facts` is unique on (document, category, entity, attribute,
    ordinal), which is what makes re-ingestion idempotent. Where two
    genuinely different facts land on the same key, the first to arrive would
    silently win and the other would vanish — the worst possible failure,
    because the surviving row looks correct.

    Rather than guess upfront whether a list's introducer is meaningful
    ("These include:" says nothing, "Expenditure can include:" says plenty),
    this only intervenes where a real collision exists, and it does so
    deterministically by qualifying the entity with the introducer.

    Qualification is decided per *run set* — every item sharing a section,
    context and attribute — rather than per colliding key. Deciding key by
    key qualifies items 1 to 4 of a seven-item list and leaves item 5 bare,
    which is worse than not qualifying at all: the same list then appears
    under two different names and no single query returns all of it.

    Any collision surviving this is reported as a warning rather than
    resolved by a coin toss.
    """
    run_sets: dict[tuple[str, str, str, str], set[str]] = {}
    for fact in facts:
        if fact.list_label:
            run_sets.setdefault(
                (fact.section_number, fact.category, fact.entity, fact.attribute), set()
            ).add(fact.list_label)

    split_runs = {key for key, labels in run_sets.items() if len(labels) > 1}

    resolved: list[ParsedFact] = []
    for fact in facts:
        run_key = (fact.section_number, fact.category, fact.entity, fact.attribute)
        if fact.list_label and run_key in split_runs:
            fact = replace(fact, entity=f"{fact.entity} — {fact.list_label}")
        resolved.append(fact)

    still: dict[tuple[str, str, str, int], set[str]] = {}
    for fact in resolved:
        still.setdefault((fact.category, fact.entity, fact.attribute, fact.ordinal), set()).add(fact.value)
    for (category, entity, attribute, ordinal), values in still.items():
        if len(values) > 1:
            warnings.append(
                f"Two different {category} values share the identity "
                f"{entity!r}/{attribute!r}/{ordinal}: {sorted(values)}. "
                "One of them will not be stored; check the source document."
            )
    return resolved


def _rule_title_lines(tagged: list[_Line], position: int) -> tuple[str, int]:
    """Join a rule's title across the physical lines it was printed on.

    Two of this document's seven rules have titles that wrap in the PDF:

        Rule 2 — Do not call the current DeKUTSO Chairperson "President"
        automatically.

    Without this the tail of the title is silently reclassified as the first
    line of the rule's *body*, and the guardrail that exists to stop the
    assistant calling the Chairperson "President" ends up stored as a
    rule whose body begins with the word "automatically." — at which point
    the instruction it is supposed to carry is truncated.
    """
    match = _RULE.match(tagged[position].text.strip())
    title = match.group(2).strip()
    cursor = position + 1
    while cursor < len(tagged) and tagged[cursor].section_number == tagged[position].section_number:
        following = tagged[cursor].text.strip()
        if not following:
            cursor += 1
            continue
        # Only a continuation if it is not one of the things that ends a
        # title, and if the title so far looks unfinished: no terminal
        # punctuation. "Do not invent ambulance booking websites." already
        # ends its own sentence, so the next line is body, not title.
        if (
            _RULE.match(following)
            or _is_heading(following)
            or _BULLET.match(following)
            or _ENUMERATED.match(following)
            or _STEP.match(following)
            or title.endswith((".", "!", "?", ":", ";"))
        ):
            break
        title = f"{title} {following}"
        cursor += 1
    return title, cursor


def _extract_guardrails(tagged: list[_Line], warnings: list[str]) -> list[ParsedGuardrail]:
    guardrails: list[ParsedGuardrail] = []
    seen: set[int] = set()
    for position, line in enumerate(tagged):
        match = _RULE.match(line.text.strip())
        if not match:
            continue
        number = int(match.group(1))
        title, cursor = _rule_title_lines(tagged, position)
        # Anything above the first rule is the section's framing prose — here,
        # "An AI system trained on this information should follow these rules".
        # It is not part of Rule 1, and folding it in would state a rule the
        # document never gave.
        body_lines: list[str] = []
        while cursor < len(tagged) and tagged[cursor].section_number == line.section_number:
            following = tagged[cursor].text.strip()
            if _RULE.match(following) or _is_heading(following):
                break
            if following:
                body_lines.append(following)
            cursor += 1
        if number in seen:
            warnings.append(f"Rule {number} appears more than once; only the first was kept as a guardrail.")
            continue
        seen.add(number)
        guardrails.append(ParsedGuardrail(rule_number=number, title=title, body=_join_paragraphs(body_lines)))
    return guardrails
