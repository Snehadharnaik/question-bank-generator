# Required Libraries
import pandas as pd
import re
from docx import Document
from docx.shared import Inches
from docx.oxml.ns import qn
from docx.shared import Pt
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.shared import RGBColor
import streamlit as st
from docx import Document as DocxDocument
from docx.shared import Pt

# ------------------ Helper Functions ------------------

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

def extract_keyword(question):
    keywords = ["chlorine", "coagulation", "disinfection", "aeration", "filtration", 
                "treatment", "pollution", "pump", "settling", "cyclone", "softening"]
    question = question.lower()
    for word in keywords:
        if word in question:
            return word
    words = re.findall(r'\b[a-zA-Z]{4,}\b', question)
    return words[0] if words else "General"

def read_unit_mapping_from_docx(docx_path):
    unit_mapping = {}
    doc = DocxDocument(docx_path)
    for para in doc.paragraphs:
        text = para.text.strip()
        match = re.match(r'^(\d+)\s+(.+)', text)
        if match:
            unit_no, unit_name = match.groups()
            unit_mapping[unit_no.strip()] = unit_name.strip()
    print("Extracted Unit Mapping:", unit_mapping)
    return unit_mapping


# ------------------ Generate DOCX ------------------
def generate_question_bank_docx(df, unit_mapping, output_path):
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

        bloom = detect_bloom_level(question)
        difficulty = assign_difficulty(bloom)
        qtype = classify_question_type(question)
        keyword = extract_keyword(question)
        unit_name = unit_mapping.get(unit.strip(), "[Unit name not found]")

        table = doc.add_table(rows=0, cols=2)
        table.alignment = WD_TABLE_ALIGNMENT.LEFT
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
        add_row("Tag", unit_name)
        add_row("Keywords", keyword)
        add_row("Blooms Taxonomy", bloom)
        add_row("Course Outcome", "CO1")
        add_row("Teacher ID", f"<{teacher_id}>")
        add_row("Year", "<System updates>")
        add_row("Year asked", "<System updates>")
        add_row("Frequency", "<System updates>")

        doc.add_page_break()

    doc.save(output_path)
    print(f"✅ Question bank DOCX generated: {output_path}")

# ------------------ Streamlit UI ------------------
def streamlit_ui():
    st.title("📚 Question Bank Generator - DOCX")

    qfile = st.file_uploader("Upload Questions CSV", type=["csv"])
    sfile = st.file_uploader("Upload Syllabus DOCX", type=["docx"])

    if qfile and sfile:
        df = pd.read_csv(qfile)
        unit_map = read_unit_mapping_from_docx(sfile)

        if st.button("Generate Question Bank (.docx)"):
            out_path = "QuestionBank_Output.docx"
            generate_question_bank_docx(df, unit_map, out_path)
            with open(out_path, "rb") as f:
                st.download_button("Download DOCX File", f, file_name="QuestionBank_Output.docx")

if __name__ == "__main__":
    streamlit_ui()
