import os
import io
import textwrap
from flask import Flask, request, send_file, render_template, abort
import PyPDF2
from googletrans import Translator
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

app = Flask(__name__)

# Path to a Devanagari-capable TTF font file you must download (example: NotoSansDevanagari-Regular.ttf)
# Place the TTF in the same folder as app.py or give absolute path.
DEVANAGARI_TTF = "NotoSansDevanagari-Regular.ttf"

# Register font
if not os.path.exists(DEVANAGARI_TTF):
    print(f"WARNING: Font file {DEVANAGARI_TTF} not found. Hindi may not render correctly.")
else:
    pdfmetrics.registerFont(TTFont("Deva", DEVANAGARI_TTF))

translator = Translator()

@app.route("/")
def index():
    return render_template("index.html")

def extract_text_from_pdf_bytes(pdf_bytes):
    reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    for i in range(len(reader.pages)):
        text = reader.pages[i].extract_text()
        pages.append(text or "")
    return pages

def create_hindi_pdf_from_texts(text_pages, out_stream):
    # create PDF with ReportLab, embedding Devanagari font
    c = canvas.Canvas(out_stream, pagesize=A4)
    width, height = A4

    # choose font (fallback to Helvetica if Deva not registered)
    font_name = "Deva" if "Deva" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
    font_size = 12
    line_height = font_size + 6
    left_margin = 40
    right_margin = 40
    usable_width = width - left_margin - right_margin
    max_chars_per_line = 80  # rough wrap; adjust

    for page_text in text_pages:
        if not page_text:
            c.showPage()
            continue

        # We will wrap lines to fit page width — better layout engines are possible.
        # Use simple wrapping by characters (works reasonably for Devanagari)
        # Use textwrap to break into lines roughly
        wrapper = textwrap.TextWrapper(width=max_chars_per_line, break_long_words=True, replace_whitespace=False)
        lines = []
        for paragraph in page_text.splitlines():
            paragraph = paragraph.strip()
            if not paragraph:
                lines.append("")  # preserve blank line
            else:
                wrapped = wrapper.wrap(paragraph)
                lines.extend(wrapped)

        # draw lines onto page
        y = height - 60
        c.setFont(font_name, font_size)
        for line in lines:
            if y < 60:
                c.showPage()
                c.setFont(font_name, font_size)
                y = height - 60
            # reportlab's drawString takes (x,y,text)
            c.drawString(left_margin, y, line)
            y -= line_height

        c.showPage()

    c.save()

@app.route("/translate", methods=["POST"])
def translate_endpoint():
    if 'pdf' not in request.files:
        return "No file part", 400

    f = request.files['pdf']
    if f.filename == '':
        return "No selected file", 400

    if not f.filename.lower().endswith('.pdf'):
        return "Please upload a PDF file", 400

    file_bytes = f.read()

    try:
        # 1) Extract text per page
        pages_text = extract_text_from_pdf_bytes(file_bytes)

        # 2) Translate each page's text
        translated_pages = []
        for text in pages_text:
            if not text.strip():
                translated_pages.append("")  # keep empty pages
                continue
            # Googletrans can handle larger chunks but for reliability, you can chunk if needed.
            translated = translator.translate(text, src='en', dest='hi')
            translated_pages.append(translated.text)

        # 3) Create PDF in memory
        output_stream = io.BytesIO()
        create_hindi_pdf_from_texts(translated_pages, output_stream)
        output_stream.seek(0)

        # return file as downloadable attachment
        # set a custom filename
        out_filename = os.path.splitext(f.filename)[0] + "_hindi.pdf"
        response = send_file(
            output_stream,
            as_attachment=True,
            download_name=out_filename,
            mimetype='application/pdf'
        )
        # add header so frontend can know filename
        response.headers['X-Filename'] = out_filename
        return response

    except Exception as e:
        # for debugging: return error message
        return f"Error processing file: {str(e)}", 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)
