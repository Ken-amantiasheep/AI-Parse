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
    autoplus_paths: Optional[list] = None,
    quote_path: Optional[str] = None,
    mvr_path: Optional[str] = None,
    mvr_paths: Optional[list] = None,
    application_form_path: Optional[str] = None
) -> dict:
    """
    Extract text from all documents
    
    Args:
        autoplus_path: Path to a single Autoplus document (for backward compatibility)
        autoplus_paths: List of paths to Autoplus documents (takes precedence over autoplus_path)
        quote_path: Path to Quote document
        mvr_path: Path to a single MVR document (for backward compatibility)
        mvr_paths: List of paths to MVR documents (takes precedence over mvr_path)
        application_form_path: Path to Application Form document
    
    Returns:
        Dictionary containing document names and content
        Multiple Autoplus documents will be stored as "Autoplus_1", "Autoplus_2", etc.
        Multiple MVR documents will be stored as "MVR_1", "MVR_2", etc.
    """
    documents = {}
    
    # Handle multiple Autoplus files
    autoplus_list = []
    if autoplus_paths:
        autoplus_list = autoplus_paths if isinstance(autoplus_paths, list) else [autoplus_paths]
    elif autoplus_path:
        autoplus_list = [autoplus_path]
    
    if autoplus_list:
        for idx, autoplus_file in enumerate(autoplus_list, start=1):
            if autoplus_file and os.path.exists(autoplus_file):
                print(f"Reading Autoplus document {idx}: {os.path.basename(autoplus_file)}")
                if len(autoplus_list) == 1:
                    # Single Autoplus file - use "Autoplus" for backward compatibility
                    documents["Autoplus"] = read_document(autoplus_file)
                else:
                    # Multiple Autoplus files - use "Autoplus_1", "Autoplus_2", etc.
                    documents[f"Autoplus_{idx}"] = read_document(autoplus_file)
    
    if quote_path and os.path.exists(quote_path):
        print(f"Reading Quote document: {os.path.basename(quote_path)}")
        documents["Quote"] = read_document(quote_path)
    
    # Handle multiple MVR files
    mvr_list = []
    if mvr_paths:
        mvr_list = mvr_paths if isinstance(mvr_paths, list) else [mvr_paths]
    elif mvr_path:
        mvr_list = [mvr_path]
    
    if mvr_list:
        for idx, mvr_file in enumerate(mvr_list, start=1):
            if mvr_file and os.path.exists(mvr_file):
                print(f"Reading MVR document {idx}: {os.path.basename(mvr_file)}")
                if len(mvr_list) == 1:
                    # Single MVR file - use "MVR" for backward compatibility
                    documents["MVR"] = read_document(mvr_file)
                else:
                    # Multiple MVR files - use "MVR_1", "MVR_2", etc.
                    documents[f"MVR_{idx}"] = read_document(mvr_file)
    
    if application_form_path and os.path.exists(application_form_path):
        print(f"Reading Application Form: {os.path.basename(application_form_path)}")
        documents["Application_Form"] = read_document(application_form_path)
    
    if not documents:
        raise ValueError("At least one document path must be provided and exist")
    
    return documents
