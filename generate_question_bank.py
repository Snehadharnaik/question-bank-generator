import io
import re
import time
import pandas as pd
from datetime import datetime

# --- NLP (spaCy) setup with safe fallback ---
try:
    import spacy
    try:
        nlp = spacy.load("en_core_web_sm")
    except Exception:
        nlp = None
except Exception:
    nlp = None

from docx import Document
from docx.shared import Pt
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

import streamlit as st

# ------------------ Utilities ------------------
GENERIC_WORDS = {
    "this", "that", "which", "these", "those", "something", "someone",
    "anyone", "anything", "everything", "nothing", "introduction", "overview",
    "system", "method", "process", "types", "application", "uses", "concept"
}

EXPECTED_COLUMNS = [
    "Question", "Unit", "Subunit", "Marks", "Answer", "Teacher ID", "Tag", "CO"
]

ALT_COLUMN_MAP = {
    # lowercase -> canonical
    "q": "Question",
    "question text": "Question",
    "unit no": "Unit",
    "unit number": "Unit",
    "sub-unit": "Subunit",
    "sub unit": "Subunit",
    "mark": "Marks",
    "teacher": "Teacher ID",
    "teacherid": "Teacher ID",
    "teacher_id": "Teacher ID",
    "course outcome": "CO",
}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    mapping = {}
    for col in df.columns:
        key = col.strip().lower()
        canonical = ALT_COLUMN_MAP.get(key, None)
        mapping[col] = canonical if canonical else next(
            (std for std in EXPECTED_COLUMNS if std.lower() == key), col
        )
    df = df.rename(columns=mapping)
    # Ensure all expected columns exist
    for col in EXPECTED_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df


# ------------------ Keyword Extraction ------------------
def _strip_edge_stopwords(tokens):
    if not tokens:
        return []
    # Remove leading/trailing stopwords
    i, j = 0, len(tokens) - 1
    while i <= j and tokens[i].is_stop:
        i += 1
    while j >= i and tokens[j].is_stop:
        j -= 1
    return tokens[i:j+1]


def extract_keywords_spacy(question: str) -> list:
    doc = nlp(question)
    seen = set()
    keywords = []

    # Prefer multi-word noun chunks
    for chunk in doc.noun_chunks:
        # Clean tokens: letters/digits, no punctuation
        tokens = [t for t in chunk if (t.is_alpha or t.is_digit)]
        tokens = _strip_edge_stopwords(tokens)
        if not tokens:
            continue
        text = " ".join(t.text.lower() for t in tokens)
        # length control and filters
        if 1 <= len(tokens) <= 5 and len(text) > 3 and text not in GENERIC_WORDS:
            if text not in seen:
                seen.add(text)
                keywords.append(text)
        if len(keywords) >= 3:
            break

    # Fallback to longest meaningful single words
    if len(keywords) < 1:
        words = [t.text.lower() for t in doc if t.is_alpha and not t.is_stop]
        words = sorted(set(words), key=len, reverse=True)
        for w in words:
            if w not in GENERIC_WORDS:
                keywords.append(w)
            if len(keywords) >= 3:
                break

    return keywords[:3]


def extract_keywords_fallback(question: str) -> list:
    # Simple fallback: top 3 longest words (non-stop) using a basic list
    words = re.findall(r"[A-Za-z]{3,}", question.lower())
    # very small stoplist
    stop = {"the","and","for","with","from","into","onto","about","into","using","use","uses",
            "this","that","which","these","those","such","their","your","our","its","are","is",
            "in","on","to","of","by","as","at"}
    words = [w for w in words if w not in stop and w not in GENERIC_WORDS]
    words = sorted(set(words), key=len, reverse=True)
    return words[:3] if words else ["general"]


def extract_keywords_from_question(question: str) -> str:
    try:
        if nlp is not None:
            kws = extract_keywords_spacy(question)
        else:
            kws = extract_keywords_fallback(question)
    except Exception:
        kws = extract_keywords_fallback(question)
    return ", ".join(kws) if kws else "General"


# ------------------ Bloom's Taxonomy ------------------
def detect_bloom_level(question: str) -> str:
    q = question.lower()
    bloom_keywords = {
        "L1": ["define", "list", "name", "state", "identify", "recall"],
        "L2": ["explain", "describe", "summarize", "classify", "outline"],
        "L3": ["solve", "use", "demonstrate", "compute", "apply"],
        "L4": ["compare", "differentiate", "analyze", "distinguish", "examine"],
        "L5": ["justify", "evaluate", "assess", "argue", "critique"],
        "L6": ["design", "develop", "formulate", "construct", "create"],
    }
    for level, verbs in bloom_keywords.items():
        for verb in verbs:
            if re.search(rf"\b{re.escape(verb)}\b", q):
                return level
    return "L2"


def assign_difficulty(bloom_level: str) -> str:
    return {
        "L1": "Low",
        "L2": "Low",
        "L3": "Medium",
        "L4": "Medium",
        "L5": "High",
        "L6": "High",
    }.get(bloom_level, "Medium")


def classify_question_type(question: str) -> str:
    return (
        "P" if any(w in question.lower() for w in ["calculate", "solve", "determine", "find", "compute"]) else "T"
    )


# ------------------ Unit Mapping from DOCX ------------------
def read_unit_mapping_from_docx(docx_file) -> dict:
    unit_mapping = {}
    doc = Document(docx_file)

    # Parse plain paragraphs like: "1 Introduction to XYZ"
    for para in doc.paragraphs:
        text = para.text.strip()
        m = re.match(r"^(\d+)\s+(.+)$", text)
        if m:
            unit_no, unit_name = m.groups()
            unit_mapping[unit_no.strip()] = unit_name.strip()

    # Parse simple 2-column tables (Unit No | Title)
    for tbl in doc.tables:
        for row in tbl.rows:
            if len(row.cells) >= 2:
                left = row.cells[0].text.strip()
                right = row.cells[1].text.strip()
                if re.fullmatch(r"\d+", left) and right:
                    unit_mapping[left] = right
    return unit_mapping


# ------------------ DOCX Helpers ------------------
def set_cell_text(cell, text: str, bold: bool = False, font_name: str = "Calibri", font_size_pt: int = 11):
    # Clear existing content
    cell.text = ""
    p = cell.paragraphs[0]
    run = p.add_run(str(text))
    run.bold = bold
    font = run.font
    font.name = font_name
    font.size = Pt(font_size_pt)


def add_kv_row(table, label, value, bold_value=False):
    row_cells = table.add_row().cells
    set_cell_text(row_cells[0], label, bold=False)
    set_cell_text(row_cells[1], value, bold=bold_value)


def generate_question_bank_docx(df: pd.DataFrame, unit_mapping: dict, output_stream: io.BytesIO, bold_keywords: bool = False, show_single_char_difficulty: bool = False):
    df = df.copy()
    df.fillna("", inplace=True)

    doc = Document()

    for index, row in df.iterrows():
        qno = index + 1
        question = str(row.get("Question", "")).strip()
        unit = str(row.get("Unit", "")).strip()
        subunit = str(row.get("Subunit", "")).strip()
        marks = str(row.get("Marks", "")).strip()
        answer = str(row.get("Answer", "")).strip()
        teacher_id = str(row.get("Teacher ID", "")).strip()
        tag = str(row.get("Tag", "")).strip()
        co = str(row.get("CO", "")).strip() or "CO1"

        bloom = detect_bloom_level(question)
        difficulty = assign_difficulty(bloom)
        qtype = classify_question_type(question)
        keyword_str = extract_keywords_from_question(question)

        unit_name = unit_mapping.get(unit, tag if tag else "[Unit name not found]")

        table = doc.add_table(rows=0, cols=2)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.style = "Table Grid"

        add_kv_row(table, "Question No.", qno)
        add_kv_row(table, "Question", question)
        add_kv_row(table, "Unit", f"Unit {unit}")
        add_kv_row(table, "Subunit", subunit)
        add_kv_row(table, "Marks", marks)
        diff_val = difficulty[0].upper() if show_single_char_difficulty else difficulty
        add_kv_row(table, "Difficulty", diff_val)
        add_kv_row(table, "Answer", answer)
        add_kv_row(table, "Question Type", qtype)
        add_kv_row(table, "Tag", unit_name)
        add_kv_row(table, "Keywords", keyword_str, bold_value=bold_keywords)
        add_kv_row(table, "Blooms Taxonomy", bloom)
        add_kv_row(table, "Course Outcome", co)
        add_kv_row(table, "Teacher ID", f"<{teacher_id}>")
        add_kv_row(table, "Year", "<System updates>")
        add_kv_row(table, "Year asked", "<System updates>")
        add_kv_row(table, "Frequency", "<System updates>")

        # Space between question records
        doc.add_paragraph("")
        doc.add_page_break()

    doc.save(output_stream)


# ------------------ Streamlit UI ------------------
def streamlit_ui():
    st.title("📚 Question Bank Generator — DOCX with Multi-word Keywords")

    st.write("Upload your Questions CSV. Optionally upload a Syllabus DOCX to map Unit numbers → Unit titles (used as Tag when Tag is empty).")

    c1, c2 = st.columns(2)
    with c1:
        qfile = st.file_uploader("Upload Questions CSV", type=["csv"])
    with c2:
        sfile = st.file_uploader("Upload Syllabus DOCX (optional)", type=["docx"])

    bold_keywords = st.checkbox("Bold the extracted Keywords in the DOCX", value=True)
    single_char_diff = st.checkbox("Show Difficulty as a single letter (L/M/H)", value=False)

    if qfile is not None:
        try:
            df = pd.read_csv(qfile)
        except Exception:
            qfile.seek(0)
            df = pd.read_excel(qfile)
        df = normalize_columns(df)

        # Quick preview
        st.subheader("Preview (first 10 rows)")
        st.dataframe(df.head(10))

        unit_map = {}
        if sfile is not None:
            try:
                unit_map = read_unit_mapping_from_docx(sfile)
                if unit_map:
                    st.success(f"Loaded {len(unit_map)} unit mappings from syllabus file.")
                else:
                    st.info("No unit mappings detected in the syllabus file. We'll use Tag from CSV.")
            except Exception as e:
                st.warning(f"Couldn't read syllabus mapping: {e}")

        if st.button("Generate Question Bank (.docx)"):
            buffer = io.BytesIO()
            generate_question_bank_docx(
                df, unit_map, buffer, bold_keywords=bold_keywords, show_single_char_difficulty=single_char_diff
            )
            buffer.seek(0)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            fname = f"QuestionBank_Output_{timestamp}.docx"
            st.download_button(
                label="Download DOCX File",
                data=buffer,
                file_name=fname,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

            # Guidance if spaCy wasn't available
            if nlp is None:
                st.info(
                    "spaCy model not detected. Keywords were generated using a fallback method.\n"
                    "For best results, install spaCy and the English model:\n\n"
                    "pip install spacy\n"
                    "python -m spacy download en_core_web_sm"
                )


if __name__ == "__main__":
    streamlit_ui()
