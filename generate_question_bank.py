# app.py
import io
import re
import pandas as pd
from datetime import datetime
import streamlit as st
from docx import Document
from docx.shared import Pt
from docx.enum.table import WD_TABLE_ALIGNMENT

"""
Single-file Question Bank app with STRICT multi-word keyword extraction.

Guarantees:
  • Keywords are multi-word noun-phrase style (2–6 tokens) derived from the question only
  • Works WITHOUT spaCy (heuristic RAKE-like extraction); uses spaCy noun_chunks if available
  • Live preview of extracted keywords before generating DOCX

Run:
  pip install streamlit python-docx pandas
  (Optional, better results) pip install spacy && python -m spacy download en_core_web_sm
  streamlit run app.py
"""

# ---------------- spaCy (optional) ----------------
try:
    import spacy
    try:
        _NLP = spacy.load("en_core_web_sm")
    except Exception:
        try:
            from spacy.cli import download as _dl
            _dl("en_core_web_sm")
            _NLP = spacy.load("en_core_web_sm")
        except Exception:
            _NLP = None
except Exception:
    _NLP = None

# ---------------- Stopwords / helpers ----------------
_STOP = set("""
the and or for with from into onto about using use uses of in on to by as at this that which these those their your our its are is be been being it an a do does did can could may might should would will shall how what why when where
define description describe explain discuss briefly write list state name give show draw calculate solve determine find compute compare analyze analyse assess evaluate identify demonstrate apply design develop construct create formulate justify argue critique outline summarize classify distinguish examine
question answer marks unit subunit co teacher id year frequency keywords blooms taxonomy course outcome tag type
""".split())

_GENERIC = {"introduction","overview","system","method","methods","process","processes","concept","types","factors","steps",
            "advantages","disadvantages","merits","demerits","importance","role","effect","effects","impact","principles",
            "principle","purpose","function","functions","components","parameters","features","example","examples"}

_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]*")

def _strip_edge_stops(tokens):
    i, j = 0, len(tokens) - 1
    while i <= j and (tokens[i].lower() in _STOP or len(tokens[i]) <= 1):
        i += 1
    while j >= i and (tokens[j].lower() in _STOP or len(tokens[j]) <= 1):
        j -= 1
    return tokens[i:j+1]

def _clean_phrase(tokens):
    toks = _strip_edge_stops(tokens)
    if not toks or len(toks) < 2:      # STRICT: multi-word only
        return ""
    text = " ".join(toks).lower()
    if text in _GENERIC:
        return ""
    return text

# ----------- spaCy candidates (optional, preferred) -----------
def _candidates_spacy(text: str):
    if not _NLP:
        return []
    doc = _NLP(text)
    cands = []

    # Noun chunks
    for chunk in doc.noun_chunks:
        toks = [t.text for t in chunk if (t.is_alpha or t.is_digit or '-' in t.text)]
        ph = _clean_phrase(toks)
        if ph and 2 <= len(ph.split()) <= 6:
            cands.append(ph)

    # Named entities that look like phrases
    for ent in doc.ents:
        if ent.label_ in {"ORG","PRODUCT","WORK_OF_ART","EVENT","FAC","GPE","LAW"}:
            toks = [t.text for t in ent if (t.is_alpha or t.is_digit or '-' in t.text)]
            ph = _clean_phrase(toks)
            if ph:
                cands.append(ph)

    # Unique preserve order
    seen, res = set(), []
    for ph in cands:
        if ph not in seen:
            seen.add(ph); res.append(ph)
    return res

# ----------- Heuristic RAKE-like multi-word extraction -----------
def _candidates_rake(text: str):
    # 1) quoted phrases first
    out, seen = [], set()
    for q in re.findall(r"['\"]([^'\"]{3,80})['\"]", text):
        toks = [t for t in _WORD.findall(q)]
        ph = _clean_phrase(toks)
        if ph and ph not in seen:
            seen.add(ph); out.append(ph)

    # 2) split by stopwords to get candidate chunks
    tokens = _WORD.findall(text)
    chunks, cur = [], []
    for w in tokens:
        lw = w.lower()
        if lw in _STOP:
            if cur:
                chunks.append(cur); cur = []
        else:
            cur.append(w)
    if cur:
        chunks.append(cur)

    # degree/frequency scores
    freq, deg = {}, {}
    for ch in chunks:
        for w in ch:
            lw = w.lower()
            freq[lw] = freq.get(lw, 0) + 1
            deg[lw]  = deg.get(lw, 0) + (len(ch) - 1)
    scores = {w: (deg[w] + freq[w]) / freq[w] for w in freq}

    scored = []
    for ch in chunks:
        if 2 <= len(ch) <= 6:  # multi-word only
            ph = _clean_phrase([w.lower() for w in ch])
            if not ph or ph in seen:
                continue
            s = sum(scores.get(w.lower(), 1.0) for w in ch)
            scored.append((s, ph))
    scored.sort(key=lambda x: (-x[0], -len(x[1])))

    for _, ph in scored:
        if ph not in seen:
            seen.add(ph); out.append(ph)

    # unique list already
    return out

# ----------- Public: always returns multi-word unless impossible -----------
def extract_keywords(text: str, max_keywords: int = 3):
    if not text or not str(text).strip():
        return []

    phrases = []

    # Prefer spaCy
    phrases.extend(_candidates_spacy(text))

    # Add heuristic
    if len(phrases) < max_keywords:
        extras = _candidates_rake(text)
        seen = set(phrases)
        for ph in extras:
            if ph not in seen:
                phrases.append(ph); seen.add(ph)
            if len(phrases) >= max_keywords:
                break

    # Last resort: build bigrams/trigrams from non-stop tokens (still multi-word)
    if not phrases:
        tokens = [w.lower() for w in _WORD.findall(text) if w.lower() not in _STOP]
        for n in (3, 2):
            for i in range(0, max(0, len(tokens)-n+1)):
                cand = " ".join(tokens[i:i+n])
                if len(cand) >= 4 and cand not in _GENERIC:
                    phrases.append(cand)
                    if len(phrases) >= max_keywords:
                        break
            if phrases:
                break

    # Ensure multi-word only
    phrases = [ph for ph in phrases if len(ph.split()) >= 2]
    # Dedup while preserving order
    seen, out = set(), []
    for ph in phrases:
        if ph not in seen:
            seen.add(ph); out.append(ph)
        if len(out) >= max_keywords:
            break
    return out

# ---------------- CSV normalization ----------------
_EXPECTED = ["Question","Unit","Subunit","Marks","Answer","Teacher ID","Tag","CO"]

def normalize_columns(df):
    for col in _EXPECTED:
        if col not in df.columns:
            df[col] = ""
    return df

# ---------------- DOCX helpers ----------------
def _set_cell(cell, text, bold=False):
    cell.text = ""
    run = cell.paragraphs[0].add_run(str(text))
    run.bold = bold
    f = run.font
    f.name = "Calibri"
    f.size = Pt(11)

def _row(table, label, value, bold_val=False):
    c = table.add_row().cells
    _set_cell(c[0], label)
    _set_cell(c[1], value, bold_val)

# ---------------- Bloom/Type/Difficulty (unchanged) ----------------
def detect_bloom_level(question):
    q = str(question).lower()
    bloom = {
        "L1": ["define","list","name","state","identify","recall"],
        "L2": ["explain","describe","summarize","classify","outline"],
        "L3": ["solve","use","demonstrate","compute","apply"],
        "L4": ["compare","differentiate","analyze","distinguish","examine"],
        "L5": ["justify","evaluate","assess","argue","critique"],
        "L6": ["design","develop","formulate","construct","create"],
    }
    for lvl, verbs in bloom.items():
        for v in verbs:
            if f" {v} " in f" {q} ":
                return lvl
    return "L2"

def assign_difficulty(bloom_level):
    return {"L1":"Low","L2":"Low","L3":"Medium","L4":"Medium","L5":"High","L6":"High"}.get(bloom_level,"Medium")

def classify_question_type(question):
    return "P" if any(w in str(question).lower() for w in ["calculate","solve","determine","find","compute"]) else "T"

# ---------------- DOCX generation ----------------
def generate_docx(df, unit_mapping, out_stream, bold_keywords=True, single_char_diff=False):
    doc = Document()
    for idx, row in df.iterrows():
        qno = idx + 1
        question = str(row.get("Question",""))
        unit = str(row.get("Unit",""))
        subunit = str(row.get("Subunit",""))
        marks = str(row.get("Marks",""))
        answer = str(row.get("Answer",""))
        teacher = str(row.get("Teacher ID",""))
        tag = str(row.get("Tag",""))
        co = str(row.get("CO","")) or "CO1"

        bloom = detect_bloom_level(question)
        diff = assign_difficulty(bloom)
        qtype = classify_question_type(question)
        kw_list = extract_keywords(question, max_keywords=3)
        keywords_str = ", ".join(kw_list) if kw_list else "general"

        unit_name = unit_mapping.get(unit, tag if tag else "[Unit name not found]")

        tbl = doc.add_table(rows=0, cols=2)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        tbl.style = "Table Grid"

        _row(tbl, "Question No.", qno)
        _row(tbl, "Question", question)
        _row(tbl, "Unit", f"Unit {unit}")
        _row(tbl, "Subunit", subunit)
        _row(tbl, "Marks", marks)
        _row(tbl, "Difficulty", (diff[0].upper() if single_char_diff else diff))
        _row(tbl, "Answer", answer)
        _row(tbl, "Question Type", qtype)
        _row(tbl, "Tag", unit_name)
        _row(tbl, "Keywords", keywords_str, bold_val=bold_keywords)
        _row(tbl, "Blooms Taxonomy", bloom)
        _row(tbl, "Course Outcome", co)
        _row(tbl, "Teacher ID", f"<{teacher}>")
        _row(tbl, "Year", "<System updates>")
        _row(tbl, "Year asked", "<System updates>")
        _row(tbl, "Frequency", "<System updates>")

        doc.add_page_break()

    doc.save(out_stream)

# ---------------- Syllabus mapping (optional) ----------------
def read_unit_mapping_from_docx(docx_file):
    from docx import Document as _Doc
    mapping = {}
    try:
        syl = _Doc(docx_file)
        for para in syl.paragraphs:
            txt = para.text.strip()
            m = re.match(r"^(\d+)\s+(.+)$", txt)
            if m:
                mapping[m.group(1)] = m.group(2).strip()
        for tbl in syl.tables:
            for row in tbl.rows:
                if len(row.cells) >= 2:
                    left = row.cells[0].text.strip()
                    right = row.cells[1].text.strip()
                    if re.fullmatch(r"\d+", left) and right:
                        mapping[left] = right
    except Exception:
        pass
    return mapping

# ---------------- Streamlit UI ----------------
def main():
    st.title("📚 Question Bank — Single File (FORCED Multi‑word Keywords)")
    status = "spaCy ✅ noun‑chunks" if _NLP else "No spaCy ❌ (using multi‑word heuristic)"
    st.caption(status)

    c1, c2 = st.columns(2)
    with c1:
        qfile = st.file_uploader("Upload Questions CSV", type=["csv","xlsx","xls"])
    with c2:
        sfile = st.file_uploader("Upload Syllabus DOCX (optional)", type=["docx"])

    bold_kw = st.checkbox("Bold Keywords in DOCX", value=True)
    diff_letter = st.checkbox("Show Difficulty as single letter (L/M/H)", value=False)

    if qfile is not None:
        # Read CSV/Excel
        try:
            df = pd.read_csv(qfile)
        except Exception:
            qfile.seek(0)
            df = pd.read_excel(qfile)
        df = normalize_columns(df)
        df.fillna("", inplace=True)

        # Live preview (so you can confirm multi‑word BEFORE downloading)
        prev = df.copy()
        prev["_Keywords (multi‑word)"] = prev["Question"].astype(str).apply(lambda x: ", ".join(extract_keywords(x, 3)) or "")
        st.subheader("Preview (first 15 rows)")
        st.dataframe(prev.head(15))

        # Syllabus mapping
        unit_map = {}
        if sfile is not None:
            unit_map = read_unit_mapping_from_docx(sfile)
            if unit_map:
                st.success(f"Loaded {len(unit_map)} unit mappings from syllabus file.")
            else:
                st.info("No unit mappings detected. Will use Tag from CSV.")

        if st.button("Generate Question Bank (.docx)"):
            buf = io.BytesIO()
            generate_docx(df, unit_map, buf, bold_keywords=bold_kw, single_char_diff=diff_letter)
            buf.seek(0)
            st.download_button(
                "Download DOCX",
                buf,
                file_name=f"QuestionBank_Output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

if __name__ == "__main__":
    main()
