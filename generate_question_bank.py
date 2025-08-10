# =======================
# Question Bank Generator
# =======================

import pandas as pd
import re
import subprocess
import sys
import streamlit as st
from docx import Document
from docx.shared import Pt
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx import Document as DocxDocument
import pdfplumber
import mammoth
import spacy

# -------- Auto-install SpaCy model if missing --------
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    subprocess.run([sys.executable, "-m", "spacy", "download", "en_core_web_sm"])
    nlp = spacy.load("en_core_web_sm")


# -------- Bloom Level Detection --------
def detect_bloom_level(question):
    question = question.lower()
    bloom_keywords = {
        "L1": ["define", "list", "name", "state"],
        "L2": ["explain", "describe", "summarize", "classify"],
        "L3": ["solve", "use", "demonstrate", "compute"],
        "L4": ["compare", "differentiate", "analyze", "distinguish"],
        "L5": ["justify", "evaluate", "assess", "argue"],
        "L6": ["design", "develop", "formulate", "construct"]
    }
    for level, verbs in bloom_keywords.items():
        for verb in verbs:
            if verb in question:
                return level
    return "L2"


def assign_difficulty(bloom_level):
    return {
        "L1": "Low",
        "L2": "Low",
        "L3": "Medium",
        "L4": "Medium",
        "L5": "High",
        "L6": "High"
    }.get(bloom_level, "Medium")


def classify_question_type(question):
    return "P" if any(word in question.lower() for word in ["calculate", "solve", "determine", "find"]) else "T"


# -------- File Reading (Syllabus) --------
def extract_text_from_file(file_path):
    if file_path.lower().endswith(".docx"):
        doc = DocxDocument(file_path)
        return "\n".join([p.text for p in doc.paragraphs])
    elif file_path.lower().endswith(".doc"):
        with open(file_path, "rb") as doc_file:
            result = mammoth.extract_raw_text(doc_file)
            return result.value
    elif file_path.lower().endswith(".pdf"):
        text = ""
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                if page.extract_text():
                    text += page.extract_text() + "\n"
        return text
    else:
        return ""


def extract_keywords_from_syllabus(file_path):
    syllabus_text = extract_text_from_file(file_path)
    doc = nlp(syllabus_text)
    terms = set()

    for chunk in doc.noun_chunks:
        phrase = chunk.text.strip().lower()
        if len(phrase) > 3 and not phrase.isnumeric():
            terms.add(phrase)

    return terms


def extract_keyword_from_question(question, syllabus_terms):
    doc = nlp(question)

    # First try: match noun phrases from syllabus
    for chunk in doc.noun_chunks:
        phrase = chunk.text.strip().lower()
        if phrase in syllabus_terms:
            return phrase

    # Second try: return first noun phrase in question
    noun_chunks = list(doc.noun_chunks)
    if noun_chunks:
        return noun_chunks[0].text.lower()

    # Last fallback: first long word
    words = re.findall(r'\b[a-zA-Z]{4,}\b', question.lower())
    return words[0] if words else "general"


# -------- Generate DOCX --------
def generate_question_bank_docx(df, unit_mapping, syllabus_terms, output_path):
    df.fillna("", inplace=True)
    doc = Document()

    for index, row in df.iterrows():
        qno = index + 1
        question = str(row.get("Question", ""))
        unit = str(row.get("Unit", ""))
        subunit = str(row.get("Subunit", ""))
        marks = str(row.get("Marks", ""))
        answer = str(row.get("Answer", ""))
        teacher_id = str(row.get("Teacher ID", ""))
        tag = str(row.get("Tag", unit_mapping.get(unit.strip(), "[Unit name not found]")))
        co = str(row.get("CO", "CO1"))

        bloom = detect_bloom_level(question)
        difficulty = assign_difficulty(bloom)
        qtype = classify_question_type(question)
        keyword = extract_keyword_from_question(question, syllabus_terms)

        table = doc.add_table(rows=0, cols=2)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.style = 'Table Grid'

        def add_row(label, value):
            row_cells = table.add_row().cells
            row_cells[0].text = label
            row_cells[1].text = str(value)
            for cell in row_cells:
                for paragraph in cell.paragraphs:
                    run = paragraph.runs[0]
                    font = run.font
                    font.name = 'Calibri'
                    font.size = Pt(11)

        add_row("Question No.", qno)
        add_row("Question", question)
        add_row("Unit", f"Unit {unit}")
        add_row("Subunit", subunit)
        add_row("Marks", marks)
        add_row("Difficulty", difficulty[0].upper())
        add_row("Answer", answer)
        add_row("Question Type", qtype)
        add_row("Tag", tag)
        add_row("Keywords", keyword)
        add_row("Blooms Taxonomy", bloom)
        add_row("Course Outcome", co)
        add_row("Teacher ID", f"<{teacher_id}>")
        add_row("Year", "<System updates>")
        add_row("Year asked", "<System updates>")
        add_row("Frequency", "<System updates>")

        doc.add_page_break()

    doc.save(output_path)
    print(f"✅ Question bank DOCX generated: {output_path}")


# -------- Streamlit UI --------
def streamlit_ui():
    st.title("📚 Question Bank Generator - DOCX")

    qfile = st.file_uploader("Upload Questions CSV", type=["csv"])
    sfile = st.file_uploader("Upload Syllabus (optional: DOC, DOCX, PDF)", type=["docx", "doc", "pdf"])

    if qfile:
        df = pd.read_csv(qfile)

        syllabus_terms = set()
        unit_map = {}

        if sfile:
            syllabus_terms = extract_keywords_from_syllabus(sfile)
            # Optional: also map unit numbers to unit names if in syllabus
            doc_text = extract_text_from_file(sfile)
            for line in doc_text.splitlines():
                match = re.match(r'^(\d+)\s+(.+)', line.strip())
                if match:
                    unit_no, unit_name = match.groups()
                    unit_map[unit_no.strip()] = unit_name.strip()

        if st.button("Generate Question Bank (.docx)"):
            out_path = "QuestionBank_Output.docx"
            generate_question_bank_docx(df, unit_map, syllabus_terms, out_path)
            with open(out_path, "rb") as f:
                st.download_button("Download DOCX File", f, file_name="QuestionBank_Output.docx")


if __name__ == "__main__":
    streamlit_ui()
