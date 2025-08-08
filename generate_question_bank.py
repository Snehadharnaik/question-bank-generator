# Required Libraries
import pandas as pd
import re
from odf.opendocument import OpenDocumentText
from odf.text import P, H, Span
from odf.table import Table, TableRow, TableCell
from odf.style import Style, TextProperties, ParagraphProperties
from docx import Document  # for syllabus .docx reading
import streamlit as st

# ------------------ Helper Functions ------------------

def detect_bloom_level(question):
    question = question.lower()
    bloom_keywords = {
        "Remember": ["define", "list", "name", "state"],
        "Understand": ["explain", "describe", "summarize", "classify"],
        "Apply": ["solve", "use", "demonstrate", "compute"],
        "Analyze": ["compare", "differentiate", "analyze", "distinguish"],
        "Evaluate": ["justify", "evaluate", "assess", "argue"],
        "Create": ["design", "develop", "formulate", "construct"]
    }
    for level, verbs in bloom_keywords.items():
        for verb in verbs:
            if verb in question:
                return level
    return "Understand"  # default fallback

def assign_difficulty(bloom_level):
    return {
        "Remember": "Low",
        "Understand": "Low",
        "Apply": "Medium",
        "Analyze": "Medium",
        "Evaluate": "High",
        "Create": "High"
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
        bloom = detect_bloom_level(row["Question"])
        difficulty = assign_difficulty(bloom)
        qtype = classify_question_type(row["Question"])
        keyword = extract_keyword(row["Question"])
        unit_name = unit_mapping.get(str(row["Unit"]), "General")

        table = Table(name=f"Question{qno}")

        def add_row(label, value):
            tr = TableRow()
            for text in [label, str(value)]:
                cell = TableCell()
                p = P(stylename=table_style, text=text)
                cell.addElement(p)
                tr.addElement(cell)
            table.addElement(tr)

        add_row("Q.No", qno)
        add_row("Question", row["Question"])
        add_row("Unit", row["Unit"])
        add_row("Subunit", row["Subunit"])
        add_row("Marks", row["Marks"])
        add_row("Difficulty", difficulty)
        add_row("Answer", row["Answer"])
        add_row("T/P", qtype)
        add_row("Tag", unit_name)
        add_row("Keyword", keyword)
        add_row("Bloom", bloom)
        add_row("CO", "CO1")
        add_row("Teacher ID", row["Teacher ID"])
        add_row("Year", "2025")
        add_row("Year Asked", "2025")
        add_row("Frequency", "1")

        textdoc.text.addElement(table)
        textdoc.text.addElement(P(text="", stylename=table_style))

    textdoc.save(output_path)
    print(f"Question bank generated: {output_path}")

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
