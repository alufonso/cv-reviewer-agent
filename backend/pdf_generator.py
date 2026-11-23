"""
Builds the ATS-friendly PDF version of a StructuredCV.
Uses the bundled Liberation Serif font (Times-compatible, SIL OFL licensed) so
names and text in any Latin, Greek or Cyrillic script are kept intact.
"""
import io
import os
from fpdf import FPDF
from schemas import StructuredCV

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
FONT = "LiberationSerif"
BULLET = "•"


def _new_pdf() -> FPDF:
    """Creates a Letter-size PDF with the Unicode serif font registered in all four styles."""
    pdf = FPDF(unit="mm", format="Letter")
    for style, suffix in (("", "Regular"), ("B", "Bold"), ("I", "Italic"), ("BI", "BoldItalic")):
        pdf.add_font(FONT, style=style, fname=os.path.join(FONT_DIR, f"{FONT}-{suffix}.ttf"))
    return pdf

def create_pdf_from_structured_cv(cv_data: StructuredCV) -> io.BytesIO:
    """
    Renders the StructuredCV as a single-column PDF and returns it as an in-memory stream.
    """
    # 0.5 inches = 12.7 mm
    pdf = _new_pdf()
    pdf.set_margins(left=12.7, top=12.7, right=12.7)
    pdf.set_auto_page_break(auto=True, margin=12.7)
    pdf.add_page()

    # --- Header ---
    pdf.set_font(FONT, style="B", size=14)
    pdf.cell(0, 7, cv_data.header.name.upper(), align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font(FONT, style="I", size=11)
    pdf.cell(0, 5, cv_data.header.headline, align="C", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_font(FONT, size=11)
    contact_p1 = f"{cv_data.header.location}  |  {cv_data.header.phone}  |  {cv_data.header.email}"
    pdf.multi_cell(0, 5, contact_p1, align="C", new_x="LMARGIN", new_y="NEXT")
    
    contact_p2 = f"Portfolio: {cv_data.header.portfolio}  |  LinkedIn: {cv_data.header.linkedin}  |  GitHub: {cv_data.header.github}"
    pdf.multi_cell(0, 5, contact_p2, align="C", new_x="LMARGIN", new_y="NEXT")
    
    def add_section_heading(text: str):
        pdf.ln(3) # space before
        pdf.set_font(FONT, style="B", size=12)
        pdf.cell(0, 6, text, new_x="LMARGIN", new_y="NEXT")
        
        # Draw horizontal line
        x = pdf.get_x()
        y = pdf.get_y()
        pdf.line(x, y, pdf.w - pdf.r_margin, y)
        pdf.ln(1.5) # space after

    def add_bullet_paragraph(text):
        pdf.set_font(FONT, size=11)
        pdf.set_x(12.7 + 6.35) # Indent bullet
        pdf.cell(6.35, 5, BULLET)
        
        x = pdf.get_x()
        w = pdf.w - pdf.r_margin - x
        pdf.multi_cell(w, 5, text, new_x="LMARGIN", new_y="NEXT")
        pdf.set_x(12.7) # Explicitly reset X back to the standard left margin
        
    # --- Professional Summary ---
    if cv_data.summary:
        add_section_heading("Summary")
        pdf.set_font(FONT, size=11)
        pdf.multi_cell(0, 5, cv_data.summary, new_x="LMARGIN", new_y="NEXT")

    # --- Technical Skills ---
    if cv_data.skills:
        add_section_heading("Technical Skills")
        for skill_cat in cv_data.skills:
            pdf.set_font(FONT, style="B", size=11)
            pdf.write(5, skill_cat.category + ": ")
            pdf.set_font(FONT, size=11)
            pdf.write(5, skill_cat.items + "\n")

    # --- Experience ---
    if cv_data.experience:
        add_section_heading("Experience")
        for exp in cv_data.experience:
            pdf.set_font(FONT, style="B", size=11)
            pdf.cell(0, 5, exp.role, new_x="LMARGIN", new_y="NEXT")
            
            pdf.set_font(FONT, style="I", size=11)
            comp_text = f"{exp.company}  |  {exp.duration}  |  {exp.location}"
            pdf.multi_cell(0, 5, comp_text, new_x="LMARGIN", new_y="NEXT")
            
            if exp.bullets:
                for bullet in exp.bullets:
                    add_bullet_paragraph(bullet)

    # --- Projects ---
    if cv_data.projects:
        add_section_heading("Projects")
        for proj in cv_data.projects:
            pdf.ln(1)
            pdf.set_font(FONT, style="B", size=11)
            pdf.cell(0, 5, proj.name, new_x="LMARGIN", new_y="NEXT")
            
            pdf.set_font(FONT, style="I", size=11)
            tech_text = f"{proj.context}  |  {proj.technologies}  |  {proj.link}"
            pdf.multi_cell(0, 5, tech_text, new_x="LMARGIN", new_y="NEXT")
            
            if proj.bullets:
                for bullet in proj.bullets:
                    add_bullet_paragraph(bullet)

    # --- Publication ---
    if cv_data.publications:
        add_section_heading("Publication")
        for pub in cv_data.publications:
            pdf.set_font(FONT, size=11)
            pdf.multi_cell(0, 5, pub.citation, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)

    # --- Certifications ---
    if cv_data.certifications:
        add_section_heading("Certifications")
        for cert in cv_data.certifications:
            add_bullet_paragraph(f"{cert.name} - {cert.issuer}")

    # --- Education ---
    if cv_data.education:
        add_section_heading("Education")
        for edu in cv_data.education:
            pdf.ln(1)
            pdf.set_font(FONT, style="B", size=11)
            pdf.cell(0, 5, edu.institution, new_x="LMARGIN", new_y="NEXT")
            
            pdf.set_font(FONT, size=11)
            deg_text = f"{edu.degree}  |  {edu.duration}  |  {edu.gpa}"
            pdf.multi_cell(0, 5, deg_text, new_x="LMARGIN", new_y="NEXT")

    # --- Languages & Other Skills ---
    if cv_data.languages_other:
        add_section_heading("Languages & Other Skills")
        if cv_data.languages_other.languages:
            pdf.set_font(FONT, style="B", size=11)
            pdf.write(5, "Languages: ")
            pdf.set_font(FONT, size=11)
            pdf.write(5, cv_data.languages_other.languages + "\n")
            
        if cv_data.languages_other.other_skills:
            pdf.set_font(FONT, style="B", size=11)
            pdf.write(5, "Other Skills: ")
            pdf.set_font(FONT, size=11)
            pdf.write(5, cv_data.languages_other.other_skills + "\n")

    # Get output
    output_stream = io.BytesIO()
    pdf_bytes = pdf.output() 
    output_stream.write(pdf_bytes)
    output_stream.seek(0)
    return output_stream
