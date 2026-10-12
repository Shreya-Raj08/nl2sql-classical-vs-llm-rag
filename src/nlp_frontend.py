"""Shared classical NLP front-end (used by Systems 1, 2 and 3).

Pipeline (each step is shown in the interface's "Show steps" panel):
  A1 preprocess()       tokenization, lemmatization, POS tags, dependency parse, NER (spaCy)
  A2 extract_keywords() candidate keyword spans: n-grams, noun chunks, entities, numbers, quoted values
  A3 match_keywords()   keyword dictionary matching (exact / lemma / WordNet synonym / fuzzy), a simplified
                        version of the DANKE keyword-search service of Nascimento et al. (DKE 2026)
  A4 link_schema()      tables needed + join path through the foreign-key graph (Steiner tree)
  A5 detect_intent()    rule-based cues: aggregation, comparison, superlative, grouping, ordering, negation
"""
import re
from dataclasses import dataclass, asdict
from functools import lru_cache

import networkx as nx
import spacy
from nltk.corpus import wordnet as wn
from rapidfuzz import fuzz, process

from src.spider_data import get_schema, read_text_values

# Common abbreviations found in database column names
ABBREVIATIONS = {
    "tot": "total", "cred": "credit", "dept": "department", "num": "number", "no": "number",
    "amt": "amount", "addr": "address", "qty": "quantity", "avg": "average", "dob": "date of birth",
    "yr": "year", "emp": "employee", "mgr": "manager", "desc": "description", "pct": "percent",
    "ppl": "people", "sec": "section", "bldg": "building", "loc": "location", "pop": "population",
    "hp": "horsepower", "mpg": "miles per gallon", "fname": "first name", "lname": "last name",
}
FUZZY_SCHEMA_THRESHOLD = 88
FUZZY_VALUE_THRESHOLD = 90
MAX_NGRAM = 4


@lru_cache(maxsize=1)
def nlp():
    return spacy.load("en_core_web_sm")


# ----------------------------------------------------------------------------------------------
# A1  Preprocessing
# ----------------------------------------------------------------------------------------------
def preprocess(question):
    doc = nlp()(question)
    return {
        "doc": doc,
        "tokens": [t.text for t in doc],
        "lemmas": [t.lemma_.lower() for t in doc],
        "pos": [t.pos_ for t in doc],
        "tags": [t.tag_ for t in doc],
        "deps": [f"{t.text} --{t.dep_}--> {t.head.text}" for t in doc],
        "entities": [(e.text, e.label_) for e in doc.ents],
        "noun_chunks": [c.text for c in doc.noun_chunks],
    }


def norm_value(text):
    """Normalise a data value for matching: lowercase, punctuation removed ("Comp. Sci." -> "comp sci")."""
    return " ".join(re.sub(r"[^\w]+", " ", text.lower()).split())


def _lemma_phrase(text):
    words = []
    for w in re.split(r"[_\s]+", text.strip().lower()):
        words.extend(ABBREVIATIONS.get(w, w).split())
    doc = nlp()(" ".join(words))
    return " ".join(t.lemma_.lower() for t in doc if not t.is_punct).strip()


def _wordnet_synonyms(phrase, max_synsets=2):
    """Synonyms of the phrase's head (last) word, e.g. 'instructor' -> 'teacher'."""
    words = phrase.split()
    if not words:
        return set()
    head = words[-1]
    syns = set()
    for s in wn.synsets(head, pos=wn.NOUN)[:max_synsets]:
        for l in s.lemma_names():
            l = l.replace("_", " ").lower()
            if l != head and len(l) > 2:
                syns.add(" ".join(words[:-1] + [l]))
    return syns


# ----------------------------------------------------------------------------------------------
# Keyword dictionary (mini-DANKE): table terms, column terms and indexed data values
# ----------------------------------------------------------------------------------------------
@dataclass
class DictEntry:
    phrase: str          # lemmatized phrase users may type
    kind: str            # "table" | "column"
    table: str
    column: str = None
    source: str = "name"  # "name" | "synonym"


@lru_cache(maxsize=64)
def keyword_dictionary(db_id):
    schema = get_schema(db_id)
    entries = []
    seen = set()

    def add(phrase, kind, table, column, source):
        key = (phrase, kind, table, column)
        if phrase and key not in seen:
            seen.add(key)
            entries.append(DictEntry(phrase, kind, table, column, source))

    for t in schema.tables:
        for p in {_lemma_phrase(t), _lemma_phrase(schema.table_natural[t])}:
            add(p, "table", t, None, "name")
            for s in _wordnet_synonyms(p):
                add(s, "table", t, None, "synonym")
    for c in schema.columns:
        for p in {_lemma_phrase(c.name), _lemma_phrase(c.natural)}:
            add(p, "column", c.table, c.name, "name")
            if c.name.lower() not in ("id",) and not c.name.lower().endswith("_id"):
                for s in _wordnet_synonyms(p):
                    add(s, "column", c.table, c.name, "synonym")

    values = {}                              # normalised value -> [(table, column, original value)]
    for (t, col), vals in read_text_values(db_id).items():
        for v in vals:
            key = norm_value(v)
            if key:
                values.setdefault(key, []).append((t, col, v))
    return {"entries": entries, "values": values, "value_keys": list(values.keys())}


# ----------------------------------------------------------------------------------------------
# A2  Keyword extraction
# ----------------------------------------------------------------------------------------------
def extract_keywords(pre):
    doc = pre["doc"]
    spans = []
    n = len(doc)
    for i in range(n):
        for j in range(i + 1, min(i + MAX_NGRAM, n) + 1):
            span = doc[i:j]
            last = span[-2] if j - i > 1 and span[-1].is_punct else span[-1]   # allow "Comp. Sci." style values
            if span[0].is_stop or span[0].is_punct or last.is_stop or last.is_punct:
                if not (j - i == 1 and span[0].like_num):
                    continue
            spans.append((i, j))
    quoted = [(m.group(1) or m.group(2)) for m in re.finditer(r'"([^"]+)"|\'([^\']+)\'', doc.text)]
    numbers = [(t.i, t.text) for t in doc if t.like_num and t.pos_ == "NUM"]
    return {"spans": spans, "quoted": quoted, "numbers": numbers}


# ----------------------------------------------------------------------------------------------
# A3  Keyword matching
# ----------------------------------------------------------------------------------------------
@dataclass
class Match:
    text: str
    start: int
    end: int
    kind: str              # "table" | "column" | "value" | "number"
    table: str = None
    column: str = None
    value: str = None
    score: float = 1.0
    how: str = "exact"     # exact | lemma | synonym | fuzzy
    alternatives: list = None   # other (table, column) candidates for ambiguous column names


def match_keywords(pre, kw, db_id):
    doc = pre["doc"]
    kd = keyword_dictionary(db_id)
    by_phrase = {}
    for e in kd["entries"]:
        by_phrase.setdefault(e.phrase, []).append(e)
    phrases = list(by_phrase.keys())

    candidates = []
    for i, j in kw["spans"]:
        span = doc[i:j]
        # shown in hints without trailing sentence punctuation ("department?" -> "department")
        sentence_punct = span[-1].is_punct and (span[-1].i == len(doc) - 1 or span[-1].text in "?!,;:")
        text = doc[i:j - 1].text if j - i > 1 and sentence_punct else span.text
        lemma = " ".join(t.lemma_.lower() for t in span if not t.is_punct)
        # ---- value matching (data values stored in the database) ----
        low = norm_value(text)
        is_valueish = any(t.pos_ in ("PROPN", "NUM") or t.text[:1].isupper() for t in span) or len(text) > 3
        if is_valueish and low in kd["values"] and not all(t.is_stop or t.is_punct for t in span):
            hits = kd["values"][low]
            t0, c0, v0 = hits[0]
            candidates.append(Match(text, i, j, "value", t0, c0, v0, 1.0, "exact",
                                    [(t, c) for t, c, _ in hits[1:]]))
        # ---- schema matching (table / column names) ----
        if lemma in by_phrase:
            ents = by_phrase[lemma]
            best = sorted(ents, key=lambda e: (e.source != "name", e.kind != "column"))
            e0 = best[0]
            how = "exact" if text.lower() == lemma else "lemma"
            if e0.source == "synonym":
                how = "synonym"
            alts = [(e.table, e.column) for e in best[1:] if e.kind == e0.kind]
            candidates.append(Match(text, i, j, e0.kind, e0.table, e0.column, None,
                                    0.9 if how == "synonym" else 1.0, how, alts))
        elif len(lemma) >= 4 and j - i <= 3:
            hit = process.extractOne(lemma, phrases, scorer=fuzz.ratio, score_cutoff=FUZZY_SCHEMA_THRESHOLD)
            if hit:
                e0 = by_phrase[hit[0]][0]
                candidates.append(Match(text, i, j, e0.kind, e0.table, e0.column, None,
                                        0.85 * hit[1] / 100, "fuzzy",
                                        [(e.table, e.column) for e in by_phrase[hit[0]][1:]]))

    # Fuzzy value matching for quoted strings and named entities (e.g. a slightly misspelt name)
    targets = list(kw["quoted"]) + [e.text for e in doc.ents if e.label_ not in ("CARDINAL", "DATE", "ORDINAL")]
    for target in targets:
        if norm_value(target) in kd["values"]:
            continue
        hit = process.extractOne(norm_value(target), kd["value_keys"], scorer=fuzz.ratio,
                                 score_cutoff=FUZZY_VALUE_THRESHOLD)
        if hit:
            t0, c0, v0 = kd["values"][hit[0]][0]
            start = next((t.i for t in doc if target.startswith(t.text)), 0)
            candidates.append(Match(target, start, start + len(target.split()), "value", t0, c0, v0,
                                    0.9 * hit[1] / 100, "fuzzy"))

    # Greedy selection: best score first, then longest span; spans may not overlap
    candidates.sort(key=lambda m: (-m.score, -(m.end - m.start), m.kind != "value"))
    chosen, used = [], set()
    for m in candidates:
        rng = set(range(m.start, m.end))
        if rng & used:
            continue
        chosen.append(m)
        used |= rng
    for idx, text in kw["numbers"]:
        if idx not in used:
            chosen.append(Match(text, idx, idx + 1, "number", value=text))
    chosen.sort(key=lambda m: m.start)
    return chosen


# ----------------------------------------------------------------------------------------------
# A4  Schema linking + join path (Steiner tree over the foreign-key graph)
# ----------------------------------------------------------------------------------------------
def fk_graph(schema):
    g = nx.Graph()
    g.add_nodes_from(schema.tables)
    for t1, c1, t2, c2 in schema.foreign_keys:
        if t1 != t2 and not g.has_edge(t1, t2):
            g.add_edge(t1, t2, on=(t1, c1, t2, c2))
    return g


def _resolve_ambiguous(matches):
    """For an ambiguous column name (e.g. 'name' exists in several tables) prefer an already-linked table."""
    linked = {m.table for m in matches if m.kind in ("table", "value") or (m.kind == "column" and not m.alternatives)}
    for m in matches:
        if m.kind == "column" and m.alternatives and m.table not in linked:
            for t, c in m.alternatives:
                if t in linked:
                    m.table, m.column = t, c
                    break


def link_schema(matches, db_id):
    schema = get_schema(db_id)
    _resolve_ambiguous(matches)
    tables = []
    for m in matches:
        if m.table and m.table not in tables:
            tables.append(m.table)
    if not tables:
        tables = [schema.tables[0]]
    g = fk_graph(schema)
    joins = []
    if len(tables) > 1:
        comps = [c for c in nx.connected_components(g)]
        best = max(comps, key=lambda c: sum(t in c for t in tables))
        terminals = [t for t in tables if t in best]
        if len(terminals) > 1:
            tree = nx.algorithms.approximation.steiner_tree(g.subgraph(best), terminals)
            # order tables so each join attaches to an already-joined table
            order = [terminals[0]]
            for u, v in nx.bfs_edges(tree, terminals[0]):
                order.append(v)
                joins.append(g.edges[u, v]["on"])
            tables = order + [t for t in tables if t not in order]
    columns = [(m.table, m.column) for m in matches if m.kind == "column"]
    columns += [(m.table, m.column) for m in matches if m.kind == "value"]
    return {"tables": tables, "columns": list(dict.fromkeys(columns)), "joins": joins}


# ----------------------------------------------------------------------------------------------
# A5  Intent cues (rule-based)
# ----------------------------------------------------------------------------------------------
COMPARATORS = [
    (("more", "than"), ">"), (("greater", "than"), ">"), (("larger", "than"), ">"), (("higher", "than"), ">"),
    (("bigger", "than"), ">"), (("older", "than"), ">"), (("long", "than"), ">"), (("at", "least"), ">="),
    (("less", "than"), "<"), (("fewer", "than"), "<"), (("lower", "than"), "<"), (("smaller", "than"), "<"),
    (("younger", "than"), "<"), (("short", "than"), "<"), (("at", "most"), "<="),
    (("over",), ">"), (("above",), ">"), (("exceed",), ">"), (("under",), "<"), (("below",), "<"),
    (("equal", "to"), "="),
]
DESC_WORDS = {"high", "highest", "large", "largest", "most", "maximum", "max", "big", "biggest", "great",
              "greatest", "old", "oldest", "long", "longest", "top", "many", "expensive"}
ASC_WORDS = {"low", "lowest", "small", "smallest", "least", "minimum", "min", "young", "youngest",
             "short", "shortest", "few", "fewest", "cheap", "cheapest"}


def detect_intent(pre):
    doc = pre["doc"]
    lem = pre["lemmas"]
    words = [t.lower_ for t in doc]          # surface words ("greater" is lemmatised to "great")
    text = " ".join(lem)
    cues = {"aggregate": None, "agg_token": None, "comparisons": [], "superlative": None,
            "group_by": False, "group_token": None, "order": None, "distinct": False,
            "negation": False, "limit": None}
    if re.search(r"\bhow many\b|\bnumber of\b|\bcount\b", text):
        cues["aggregate"] = "COUNT"
        cues["agg_token"] = next((i for i, l in enumerate(lem) if l in ("many", "number", "count")), None)
    for word, agg in (("average", "AVG"), ("mean", "AVG"), ("total", "SUM"), ("sum", "SUM"),
                      ("maximum", "MAX"), ("minimum", "MIN")):
        if word in lem and not (agg == "SUM" and cues["aggregate"] == "COUNT"):
            cues["aggregate"], cues["agg_token"] = agg, lem.index(word)
            break
    for i, t in enumerate(doc):
        if t.like_num and t.pos_ == "NUM":
            for cmp_words, op in COMPARATORS:
                k = len(cmp_words)
                if cmp_words in (tuple(words[max(0, i - k):i]), tuple(lem[max(0, i - k):i])):
                    try:
                        num = float(t.text.replace(",", ""))
                        num = int(num) if num.is_integer() else num
                    except ValueError:
                        continue
                    cues["comparisons"].append({"op": op, "value": num, "token": i, "phrase": " ".join(cmp_words)})
                    break
    for i, t in enumerate(doc):
        if t.tag_ in ("JJS", "RBS") or (t.lemma_.lower() == "most" and i + 1 < len(doc)):
            l = t.lemma_.lower()
            if l in DESC_WORDS or t.text.lower() in DESC_WORDS:
                cues["superlative"] = {"dir": "DESC", "token": i, "word": t.text}
            elif l in ASC_WORDS or t.text.lower() in ASC_WORDS:
                cues["superlative"] = {"dir": "ASC", "token": i, "word": t.text}
            if cues["superlative"]:
                break
    m = re.search(r"\btop (\d+)\b", doc.text.lower())
    if m:
        cues["limit"] = int(m.group(1))
        cues["superlative"] = cues["superlative"] or {"dir": "DESC", "token": None, "word": "top"}
    for i, l in enumerate(lem):
        if l in ("each", "every", "per"):
            cues["group_by"], cues["group_token"] = True, i
            break
    if re.search(r"\b(order|sort)\b", text) or "alphabetical" in text or "alphabetically" in doc.text.lower():
        cues["order"] = "DESC" if re.search(r"\bdescend", text) else "ASC"
    cues["distinct"] = bool(re.search(r"\b(different|distinct|unique)\b", text))
    cues["negation"] = any(t.dep_ == "neg" or t.lower_ in ("never", "without", "no") for t in doc)
    return cues


# ----------------------------------------------------------------------------------------------
# Full front-end
# ----------------------------------------------------------------------------------------------
def analyze(question, db_id):
    pre = preprocess(question)
    kw = extract_keywords(pre)
    matches = match_keywords(pre, kw, db_id)
    linking = link_schema(matches, db_id)
    intent = detect_intent(pre)
    return {"question": question, "db_id": db_id, "pre": pre, "keywords": kw,
            "matches": matches, "linking": linking, "intent": intent}


def steps_for_display(a):
    """JSON-friendly summary of every front-end step (for the 'Show steps' panel)."""
    p = a["pre"]
    return {
        "A1 tokens": p["tokens"],
        "A1 lemmas": p["lemmas"],
        "A1 POS tags": list(zip(p["tokens"], p["pos"])),
        "A1 dependency parse": p["deps"],
        "A1 named entities": p["entities"],
        "A2 noun chunks": p["noun_chunks"],
        "A3 keyword matches": [
            {k: v for k, v in asdict(m).items() if v not in (None, []) and k not in ("start", "end")}
            for m in a["matches"]],
        "A4 linked tables": a["linking"]["tables"],
        "A4 join path": [f"{t1}.{c1} = {t2}.{c2}" for t1, c1, t2, c2 in a["linking"]["joins"]],
        "A5 intent cues": {k: v for k, v in a["intent"].items() if v not in (None, False, [])},
    }
