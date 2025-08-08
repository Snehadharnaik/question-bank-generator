# 📝 Question Bank Generator Tool

This Python tool reads a question CSV and syllabus `.docx`, and auto-generates a `.odt` file formatted as a question bank with one question per page.

## ✅ Features

- Upload question list (CSV)
- Upload syllabus (Word `.docx`)
- Auto-detect Bloom’s Taxonomy level
- Assign difficulty level and question type
- Add keyword and tag from unit name
- Generate `.odt` file (1 question per page)

## 📥 Input CSV Format

| Question | Unit | Subunit | Marks | Answer | Teacher ID |
|----------|------|---------|-------|--------|------------|

## 🚀 How to Use

```bash
pip install -r requirements.txt
streamlit run generate_question_bank.py
