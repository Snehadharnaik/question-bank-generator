# Required Libraries
import pandas as pd
import re
from odf.opendocument import OpenDocumentText
from odf.text import P, H, Span, LineBreak, Section, PageBreak
from odf.table import Table, TableRow, TableCell
from odf.style import Style, TextProperties, ParagraphProperties
from docx import Document  # for syllabus .docx reading
import streamlit as st

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
    return "L2"  # default fallback

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
    words = re.findall(r'\b\w{4,}\b', question)
    return words[0] if words else "General"

def read_unit_mapping_from_docx(docx_path):
    unit_mapping = {}
    doc = Document(docx_path)
    for para in doc.paragraphs:
        if para.text.strip().lower().startswith("unit"):
            match = re.match(r"Unit\s*(\d+)\s*[:\-]\s*(.*)", para.text.strip(), re.IGNORECASE)
            if match:
                unit_no, unit_name = match.groups()
                unit_mapping[unit_no.strip()] = unit_name.strip()
    print("Extracted Unit Mapping:", unit_mapping)
    return unit_mapping

# ------------------ Main Generator ------------------

def generate_question_bank_odt(df, unit_mapping, output_path):
    df.fillna("", inplace=True)
    textdoc = OpenDocumentText()

    table_style = Style(name="TableStyle", family="paragraph")
    table_style.addElement(ParagraphProperties(numberlines="false", linenumber="0"))
    textdoc.styles.addElement(table_style)

    text_style = Style(name="TextStyle", family="text")
    text_style.addElement(TextProperties(fontsize="10pt"))
    textdoc.styles.addElement(text_style)

    for index, row in df.iterrows():
        qno = index + 1
        question = str(row.get("Question", ""))
        unit = str(row.get("Unit", ""))
        subunit = str(row.get("Subunit", ""))
        marks = str(row.get("Marks", ""))
        answer = str(row.get("Answer", ""))
        teacher_id = str(row.get("Teacher ID", ""))

        if not question:
            print(f"Skipping row {index+1}: Question field is empty.")
            continue

        bloom = detect_bloom_level(question)
        difficulty = assign_difficulty(bloom)
        qtype = classify_question_type(question)
        keyword = extract_keyword(question)
        unit_name = unit_mapping.get(unit.strip(), "[Unit name not found]")

        table = Table(name=f"Question{qno}")

        def add_row(label, value):
            tr = TableRow()
            for text in [label, str(value)]:
                cell = TableCell()
                p = P(stylename=table_style, text=text)
                cell.addElement(p)
                tr.addElement(cell)
            table.addElement(tr)

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

        textdoc.text.addElement(table)
        textdoc.text.addElement(P(text=""))  # page break padding
        textdoc.text.addElement(P(text="", stylename=table_style))  # second blank for spacing

    textdoc.save(output_path)
    print(f"✅ Question bank generated: {output_path}")

# ------------------ Streamlit UI ------------------

def streamlit_ui():
    st.title("📚 Question Bank Generator")

    qfile = st.file_uploader("Upload Questions CSV", type=["csv"])
    sfile = st.file_uploader("Upload Syllabus DOCX", type=["docx"])

    if qfile and sfile:
        df = pd.read_csv(qfile)
        unit_map = read_unit_mapping_from_docx(sfile)

        if st.button("Generate Question Bank (.odt)"):
            out_path = "QuestionBank_Output.odt"
            generate_question_bank_odt(df, unit_map, out_path)
            with open(out_path, "rb") as f:
                st.download_button("Download ODT File", f, file_name="QuestionBank_Output.odt")

if __name__ == "__main__":
    streamlit_ui()
