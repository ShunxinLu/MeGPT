"""
Vision Tools - Document processing using Qwen3-VL or similar Vision Language Models.
Supports PDFs, images, and document screenshots with OCR and structure understanding.
"""

import base64
import io
import logging
import tempfile
from pathlib import Path
from typing import Optional

import httpx
from langchain_core.tools import tool
from PIL import Image

from config import config
from database import get_connection
from utils.llm_factory import get_llm_config, _normalize_base_url
import sqlite3
from exceptions import (
    LLMError,
    ExternalServiceError,
    DatabaseError,
    MemoryServiceError,
    wrap_exception,
)

logger = logging.getLogger(__name__)

# Maximum image size for VLM (Qwen-VL recommends 1344x1344)
MAX_IMAGE_SIZE = (1344, 1344)


def _resize_image_for_vlm(image_path: str, max_size: tuple = MAX_IMAGE_SIZE) -> str:
    """Resize image and return base64-encoded version."""
    with Image.open(image_path) as img:
        # Resize if needed
        if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)

        # Convert to RGB if needed
        if img.mode != "RGB":
            img = img.convert("RGB")

        # Encode to base64
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=95)
        return base64.b64encode(buffer.getvalue()).decode()


def _call_vlm(prompt: str, image_b64: str, max_tokens: int = 4096) -> str:
    """Call the Vision Language Model (Qwen3-VL or compatible)."""
    try:
        # Use database config for LLM, falling back to env vars
        base_url, api_key, model = get_llm_config()
        # Base URL from get_llm_config already has /v1 added
        url = f"{base_url}/chat/completions"

        # Use VLM model from config if set, otherwise use active LLM model
        vlm_model = config.vlm_model or model

        logger.debug(
            f"Calling VLM at {url} with model {vlm_model}"
        )

        payload = {
            "model": vlm_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                        },
                    ],
                }
            ],
            "max_tokens": max_tokens,
            "temperature": 0.1,
        }

        response = httpx.post(url, json=payload, timeout=120)

        # Log response status for debugging
        logger.debug(f"VLM response status: {response.status_code}")

        response.raise_for_status()

        # Try to parse JSON
        try:
            result = response.json()
        except Exception as json_err:
            # Response wasn't JSON - log the raw response for debugging
            raw_text = response.text[:500]  # First 500 chars
            logger.error(f"VLM response was not JSON. Raw response: {raw_text}")
            # Check if it's HTML (error page from LM Studio)
            if "<html" in raw_text.lower() or "<!doctype" in raw_text.lower():
                _, _, vlm_model = get_llm_config()
                vlm_model = config.vlm_model or vlm_model
                raise ValueError(
                    f"LM Studio returned an HTML page instead of JSON. "
                    f"Please check that '{vlm_model}' "
                    f"is loaded in LM Studio and supports vision input."
                )
            raise ValueError(f"VLM API returned non-JSON response: {json_err}")

        # Check if response has expected structure
        if "choices" not in result:
            logger.error(
                f"VLM response missing 'choices' key. Keys: {list(result.keys())}"
            )
            raise ValueError(f"VLM API response missing 'choices': {result}")

        if not result["choices"]:
            logger.error(f"VLM response has empty 'choices' array")
            raise ValueError("VLM API returned empty choices array")

        return result["choices"][0]["message"]["content"]

    except httpx.TimeoutException as e:
        wrapped = wrap_exception(e, LLMError, operation="vlm_call")
        logger.error(f"VLM call timeout: {wrapped}")
        raise wrapped
    except httpx.HTTPStatusError as e:
        wrapped = wrap_exception(e, LLMError, operation="vlm_call")
        logger.error(f"VLM HTTP error: {wrapped}")
        raise wrapped
    except httpx.RequestError as e:
        wrapped = wrap_exception(e, LLMError, operation="vlm_call")
        logger.error(f"VLM request error: {wrapped}")
        raise wrapped
    except Exception as e:
        wrapped = wrap_exception(e, LLMError, operation="vlm_call")
        logger.error(f"VLM call failed: {wrapped}")
        raise wrapped


@tool
def extract_text_from_document(image_path: str) -> str:
    """
    Extract text from document image using Vision Language Model.

    Supports: PDFs (as images), screenshots, scanned docs, photos of documents.
    Preserves tables, lists, and document structure.

    Args:
        image_path: Path to document image
    """
    try:
        image_b64 = _resize_image_for_vlm(image_path)

        prompt = """Extract all text from this document image.
- Preserve the original structure and formatting
- Keep tables as Markdown tables
- Use bullet points for lists
- Include headers and section breaks
- If there are charts/graphs, describe them briefly

Return ONLY the extracted text, no commentary."""

        return _call_vlm(prompt, image_b64)

    except sqlite3.Error as e:
        wrapped = wrap_exception(e, DatabaseError, operation="document_extraction")
        logger.error(f"Database error during document extraction: {wrapped}")
        return f"Error processing document: {str(e)}"
    except (OSError, IOError) as e:
        wrapped = wrap_exception(
            e, ExternalServiceError, operation="document_extraction"
        )
        logger.error(f"File I/O error during document extraction: {wrapped}")
        return f"Error processing document: {str(e)}"
    except LLMError as e:
        logger.error(f"LLM error during document extraction: {e}")
        return f"Error processing document: {str(e)}"
    except Exception as e:
        wrapped = wrap_exception(
            e, ExternalServiceError, operation="document_extraction"
        )
        logger.error(f"Unexpected error during document extraction: {wrapped}")
        return f"Error processing document: {str(e)}"


@tool
def analyze_document_structure(image_path: str) -> str:
    """
    Analyze document structure - sections, tables, figures, key elements.
    Useful for understanding complex documents before full extraction.
    """
    try:
        image_b64 = _resize_image_for_vlm(image_path)

        prompt = """Analyze this document page and provide:
1. Document type (invoice, report, form, article, contract, etc.)
2. Main sections identified
3. Number of tables and brief summary of their contents
4. Any figures/charts and what they show
5. Key entities (names, dates, amounts, addresses, etc.)
6. Overall document structure

Be concise and structured."""

        return _call_vlm(prompt, image_b64, max_tokens=2048)

    except sqlite3.Error as e:
        wrapped = wrap_exception(e, DatabaseError, operation="document_analysis")
        logger.error(f"Database error during document analysis: {wrapped}")
        return f"Error analyzing document: {str(e)}"
    except (OSError, IOError) as e:
        wrapped = wrap_exception(e, ExternalServiceError, operation="document_analysis")
        logger.error(f"File I/O error during document analysis: {wrapped}")
        return f"Error analyzing document: {str(e)}"
    except LLMError as e:
        logger.error(f"LLM error during document analysis: {e}")
        return f"Error analyzing document: {str(e)}"
    except Exception as e:
        wrapped = wrap_exception(e, ExternalServiceError, operation="document_analysis")
        logger.error(f"Unexpected error during document analysis: {wrapped}")
        return f"Error analyzing document: {str(e)}"


@tool
def process_pdf_with_vision(
    pdf_path: str, max_pages: int = 20, analyze_structure: bool = False
) -> str:
    """
    Convert PDF to images and process each page with Vision Language Model.
    Falls back to PyMuPDF if pdf2image/poppler is not available.

    Args:
        pdf_path: Path to PDF file
        max_pages: Maximum pages to process (default: 20)
        analyze_structure: If True, analyze structure first before extraction
    """
    try:
        # Try pdf2image first (requires poppler)
        from pdf2image import convert_from_path

        # Check if poppler is available
        import shutil

        use_pdf2image = shutil.which("pdftoppm") is not None
        if not use_pdf2image:
            logger.info("pdf2image installed but poppler not found, using PyMuPDF")
    except ImportError:
        logger.info("pdf2image not available, trying PyMuPDF")
        use_pdf2image = False

    # Import PIL here for both paths
    try:
        from PIL import Image
        import io
    except ImportError:
        return "Error: PIL not installed. Run: pip install Pillow"

    try:
        logger.info(f"Converting PDF to images: {pdf_path}")

        # Convert PDF pages to PIL Images
        pil_images = []

        if use_pdf2image:
            # Use pdf2image (requires poppler)
            from pdf2image import convert_from_path

            try:
                # Newer API
                pil_images = convert_from_path(pdf_path, max_pages=max_pages, dpi=200)
            except TypeError:
                # Older API - don't have max_pages, get all and slice
                all_pages = convert_from_path(pdf_path, dpi=200)
                pil_images = all_pages[:max_pages]
        else:
            # Use PyMuPDF as fallback (no external dependencies)
            try:
                import fitz  # PyMuPDF

                doc = fitz.open(pdf_path)
                for page_num in range(min(len(doc), max_pages)):
                    page = doc[page_num]
                    # Render page to image (zoom for better quality)
                    mat = fitz.Matrix(2, 2)  # 2x zoom for better OCR
                    pix = page.get_pixmap(matrix=mat)
                    img_data = pix.tobytes("jpeg")
                    pil_images.append(Image.open(io.BytesIO(img_data)))
                doc.close()
            except ImportError:
                return "Error: Neither pdf2image nor PyMuPDF available. Install poppler for pdf2image, or run: pip install pymupdf"

        if not pil_images:
            return "No pages found in PDF"

        results = []
        actual_page_count = min(len(pil_images), max_pages)

        with tempfile.TemporaryDirectory() as temp_dir:
            for i in range(actual_page_count):
                temp_path = Path(temp_dir) / f"page_{i + 1}.jpg"
                pil_images[i].save(temp_path, "JPEG")

                logger.info(f"Processing page {i + 1}/{actual_page_count}")

                if analyze_structure and i == 0:
                    # Analyze first page to understand document type
                    structure = analyze_document_structure.invoke(
                        {"image_path": str(temp_path)}
                    )
                    results.append(f"=== DOCUMENT STRUCTURE ===\n{structure}\n\n")

                # Extract text from page
                text = extract_text_from_document.invoke({"image_path": str(temp_path)})
                results.append(f"=== PAGE {i + 1} ===\n{text}\n")

        full_text = "\n".join(results)
        logger.info(f"Processed {actual_page_count} pages, {len(full_text)} characters")

        return full_text

    except sqlite3.Error as e:
        wrapped = wrap_exception(e, DatabaseError, operation="pdf_processing")
        logger.error(f"Database error during PDF processing: {wrapped}")
        return f"Error processing PDF: {str(e)}"
    except (OSError, IOError) as e:
        wrapped = wrap_exception(e, ExternalServiceError, operation="pdf_processing")
        logger.error(f"File I/O error during PDF processing: {wrapped}")
        return f"Error processing PDF: {str(e)}"
    except LLMError as e:
        logger.error(f"LLM error during PDF processing: {e}")
        return f"Error processing PDF: {str(e)}"
    except Exception as e:
        wrapped = wrap_exception(e, ExternalServiceError, operation="pdf_processing")
        logger.error(f"Unexpected error during PDF processing: {wrapped}")
        return f"Error processing PDF: {str(e)}"


@tool
def search_documents(query: str, chat_id: Optional[str] = None, limit: int = 5) -> str:
    """
    Search through processed documents in the knowledge base.

    Args:
        query: Search query (full-text search)
        chat_id: Optional chat ID to filter results
        limit: Maximum results to return
    """
    try:
        from database import search_documents as db_search

        results = db_search(query, chat_id, limit)

        if not results:
            return "No documents found matching your query."

        output = []
        for doc in results:
            output.append(f"**{doc['filename']}** (ID: {doc['id'][:8]})")
            if doc.get("preview"):
                output.append(f"Preview: {doc['preview'][:200]}...")
            elif doc.get("summary"):
                output.append(f"Summary: {doc['summary'][:200]}")
            output.append("")

        return "\n".join(output)

    except sqlite3.Error as e:
        wrapped = wrap_exception(e, DatabaseError, operation="document_search")
        logger.error(f"Database error during document search: {wrapped}")
        return f"Error searching documents: {str(e)}"
    except Exception as e:
        wrapped = wrap_exception(e, ExternalServiceError, operation="document_search")
        logger.error(f"Unexpected error during document search: {wrapped}")
        return f"Error searching documents: {str(e)}"


@tool
def get_document_content(document_id: str) -> str:
    """
    Get the full content of a specific document.

    Args:
        document_id: The ID of the document to retrieve
    """
    try:
        with get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT filename, content, summary
                FROM documents
                WHERE id = ?
            """,
                (document_id,),
            )
            row = cursor.fetchone()

            if not row:
                return f"Document not found: {document_id}"

            return f"**{row['filename']}**\n\n{row['content'][:10000]}"

    except sqlite3.Error as e:
        wrapped = wrap_exception(e, DatabaseError, operation="document_retrieval")
        logger.error(f"Database error during document retrieval: {wrapped}")
        return f"Error retrieving document: {str(e)}"
    except Exception as e:
        wrapped = wrap_exception(
            e, ExternalServiceError, operation="document_retrieval"
        )
        logger.error(f"Unexpected error during document retrieval: {wrapped}")
        return f"Error retrieving document: {str(e)}"


@tool
def search_document_memory(query: str, limit: int = 5) -> str:
    """
    Search through uploaded documents using semantic search.

    This searches the vector knowledge base where facts extracted from
    your uploaded documents are stored. Much more powerful than
    simple keyword search.

    Useful for:
    - "What does my document say about X?"
    - "Find information about Y in my documents"
    - "What deadlines are mentioned?"
    - "What did the document say about budget?"

    Args:
        query: What to search for in your documents
        limit: Maximum results to return

    Returns:
        Relevant information from your documents
    """
    try:
        from tools.memory_tool import search_document_memories

        results = search_document_memories(query, user_id=config.user_id, limit=limit)

        if not results:
            return f"No relevant information found in your documents for: {query}"

        # Format results
        lines = [f"Found {len(results)} relevant facts from documents:\n"]
        for mem in results:
            lines.append(f"• {mem['memory']}")
            if mem.get("metadata", {}).get("document_filename"):
                lines.append(f"  (from: {mem['metadata']['document_filename']})")

        return "\n".join(lines)

    except sqlite3.Error as e:
        wrapped = wrap_exception(e, DatabaseError, operation="document_memory_search")
        logger.error(f"Database error during document memory search: {wrapped}")
        return f"Error searching documents: {str(e)}"
    except MemoryServiceError as e:
        logger.error(f"Memory service error during document memory search: {e}")
        return f"Error searching documents: {str(e)}"
    except Exception as e:
        wrapped = wrap_exception(
            e, ExternalServiceError, operation="document_memory_search"
        )
        logger.error(f"Unexpected error during document memory search: {wrapped}")
        return f"Error searching documents: {str(e)}"


# List of tools to export
VISION_TOOLS = [
    extract_text_from_document,
    analyze_document_structure,
    process_pdf_with_vision,
    search_documents,
    get_document_content,
    search_document_memory,
]
