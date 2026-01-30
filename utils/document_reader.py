"""
Document reader utility - Supports PDF, Word, and text files
"""
import os
from typing import Optional

def read_pdf(file_path: str) -> str:
    """Read PDF file content"""
    try:
        import pdfplumber
        text = ""
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text.strip()
    except Exception as e:
        raise Exception(f"Failed to read PDF file {file_path}: {e}")

def read_word(file_path: str) -> str:
    """Read Word document content"""
    try:
        from docx import Document
        doc = Document(file_path)
        text = "\n".join([para.text for para in doc.paragraphs])
        return text.strip()
    except Exception as e:
        raise Exception(f"Failed to read Word file {file_path}: {e}")

def read_text(file_path: str) -> str:
    """Read plain text file content"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except UnicodeDecodeError:
        # Try other encodings
        try:
            with open(file_path, 'r', encoding='gbk') as f:
                return f.read().strip()
        except:
            with open(file_path, 'r', encoding='latin-1') as f:
                return f.read().strip()
    except Exception as e:
        raise Exception(f"Failed to read text file {file_path}: {e}")

def read_document(file_path: str) -> str:
    """
    Automatically detect file type and read document content
    
    Args:
        file_path: Document file path
        
    Returns:
        Document text content
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.pdf':
        return read_pdf(file_path)
    elif ext in ['.doc', '.docx']:
        return read_word(file_path)
    elif ext in ['.txt', '.text']:
        return read_text(file_path)
    else:
        # Try to read as text file
        try:
            return read_text(file_path)
        except:
            raise ValueError(f"Unsupported file type: {ext}")

def extract_text_from_documents(
    autoplus_path: Optional[str] = None,
    quote_path: Optional[str] = None,
    mvr_path: Optional[str] = None,
    application_form_path: Optional[str] = None
) -> dict:
    """
    Extract text from all documents
    
    Returns:
        Dictionary containing document names and content
    """
    documents = {}
    
    if autoplus_path and os.path.exists(autoplus_path):
        print(f"Reading Autoplus document: {os.path.basename(autoplus_path)}")
        documents["Autoplus"] = read_document(autoplus_path)
    
    if quote_path and os.path.exists(quote_path):
        print(f"Reading Quote document: {os.path.basename(quote_path)}")
        documents["Quote"] = read_document(quote_path)
    
    if mvr_path and os.path.exists(mvr_path):
        print(f"Reading MVR document: {os.path.basename(mvr_path)}")
        documents["MVR"] = read_document(mvr_path)
    
    if application_form_path and os.path.exists(application_form_path):
        print(f"Reading Application Form: {os.path.basename(application_form_path)}")
        documents["Application_Form"] = read_document(application_form_path)
    
    if not documents:
        raise ValueError("At least one document path must be provided and exist")
    
    return documents
