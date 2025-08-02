import fitz  # PyMuPDF

def extract_important_text(pdf_path):
    important_text = []

    pdf_document = fitz.open(pdf_path)
    
    for page_number in range(pdf_document.page_count):
        page = pdf_document.load_page(page_number)
        page_text = page.get_text()

        # Exclude pages with tables
        if "Table" not in page_text:
            important_text.append(page_text)

    pdf_document.close()
    return important_text

pdf_path = "EUPD.pdf"
important_text = extract_important_text(pdf_path)

for page_text in important_text:
    print(page_text)
    print("=" * 50)
