"""
Document API Routes - Upload, list, search, and delete documents.
Integrates with vision_tools.py for PDF/image processing.
"""

import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Form
from pydantic import BaseModel

from config import config
from database import (
    create_document,
    update_document,
    get_documents,
    get_document,
    delete_document as db_delete_document,
    search_documents as db_search_documents,
)

from tools.vision_tools import process_pdf_with_vision, extract_text_from_document

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])

# Allowed file extensions
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".txt", ".md", ".docx"}

# Upload directory
UPLOAD_DIR = config.data_dir / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class DocumentResponse(BaseModel):
    """Response model for document operations."""
    id: str
    filename: str
    file_type: str
    summary: Optional[str] = None
    chunk_count: int = 0
    status: str
    created_at: str


class SearchResponse(BaseModel):
    """Response model for document search."""
    results: list[dict]
    total: int


def get_file_extension(filename: str) -> str:
    """Get file extension from filename."""
    return Path(filename).suffix.lower()


def is_allowed_file(filename: str) -> bool:
    """Check if file type is allowed."""
    return get_file_extension(filename) in ALLOWED_EXTENSIONS


async def process_document_file(
    doc_id: str,
    file_path: Path,
    filename: str,
    chat_id: Optional[str],
):
    """
    Background task to process document with VLM and ingest to memory.
    """
    try:
        logger.info(f"Processing document {doc_id}: {filename}")

        file_ext = get_file_extension(filename)
        content = ""
        summary = ""

        if file_ext == ".pdf":
            # Try VLM first, fall back to text extraction
            vlm_failed = False
            try:
                content = process_pdf_with_vision.invoke({
                    "pdf_path": str(file_path),
                    "max_pages": 20,
                    "analyze_structure": True
                })
                # Check if VLM returned an error message instead of content
                if content.startswith("Error:") or content.startswith("[Could not"):
                    logger.warning(f"VLM processing failed: {content[:100]}")
                    vlm_failed = True
                elif not content or len(content.strip()) < 10:
                    logger.warning("VLM returned empty or too short content")
                    vlm_failed = True
            except Exception as vlm_err:
                logger.warning(f"VLM processing failed for PDF, trying text extraction: {vlm_err}")
                vlm_failed = True

            # Fallback to pdfplumber if VLM failed
            if vlm_failed:
                try:
                    import pdfplumber
                    with pdfplumber.open(file_path) as pdf:
                        pages_text = []
                        for page in pdf.pages[:20]:  # Limit to 20 pages
                            text = page.extract_text()
                            if text:
                                pages_text.append(text)
                        content = "\n\n".join(pages_text)
                    if not content:
                        content = "[Could not extract any text from PDF]"
                    else:
                        summary = content[:500] + "..." if len(content) > 500 else content
                        logger.info(f"Extracted {len(content)} characters using pdfplumber")
                except ImportError:
                    logger.error("pdfplumber not installed, cannot extract text from PDF")
                    content = "[Could not extract text from PDF: pdfplumber not installed]"
                except Exception as pdf_err:
                    logger.error(f"PDF text extraction failed: {pdf_err}")
                    content = f"[Could not extract text from PDF: {pdf_err}]"

        elif file_ext in [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff"]:
            # Process image with VLM - no fallback for images
            try:
                content = extract_text_from_document.invoke({
                    "image_path": str(file_path)
                })
            except Exception as vlm_err:
                logger.error(f"Image processing failed: {vlm_err}")
                content = f"[Could not process image. VLM error: {vlm_err}]"

        elif file_ext in [".txt", ".md"]:
            # Read text file directly
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            summary = content[:500] + "..." if len(content) > 500 else content
        else:
            # For other files, just store metadata
            content = f"[Binary file: {filename}]"

        # Generate summary if not already set
        if not summary and content:
            summary = content[:500] + "..." if len(content) > 500 else content

        # Update document with processed content
        update_document(
            document_id=doc_id,
            content=content,
            summary=summary,
            status="completed"
        )

        # Ingest document into vector memory (chunk + embed + store in Qdrant)
        if content and len(content) > 100 and not content.startswith("["):  # Only ingest if there's meaningful content
            from tools.memory_tool import ingest_document_to_memory

            logger.info(f"Ingesting document {doc_id} into vector memory...")
            memory_result = ingest_document_to_memory(
                document_id=doc_id,
                filename=filename,
                content=content,
                chat_id=chat_id,
            )

            if memory_result.get("success"):
                logger.info(f"Document {doc_id} ingested: {memory_result.get('message', '')}")
            else:
                logger.warning(f"Document {doc_id} memory ingestion failed: {memory_result.get('error', '')}")

        logger.info(f"Document {doc_id} processed successfully: {len(content)} characters")

    except Exception as e:
        logger.error(f"Failed to process document {doc_id}: {e}")
        # Mark as failed
        update_document(document_id=doc_id, status="failed")


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    chat_id: Optional[str] = None,
    limit: int = 50,
):
    """List all documents, optionally filtered by chat."""
    docs = get_documents(chat_id=chat_id, limit=limit)
    return [
        DocumentResponse(
            id=d["id"],
            filename=d["filename"],
            file_type=d["file_type"],
            summary=d.get("summary"),
            chunk_count=d.get("chunk_count", 0),
            status=d.get("status", "completed"),
            created_at=d["created_at"],
        )
        for d in docs
    ]


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document_by_id(document_id: str):
    """Get a single document by ID."""
    doc = get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    return DocumentResponse(
        id=doc["id"],
        filename=doc["filename"],
        file_type=doc["file_type"],
        summary=doc.get("summary"),
        chunk_count=doc.get("chunk_count", 0),
        status=doc.get("status", "completed"),
        created_at=doc["created_at"],
    )


@router.get("/{document_id}/content")
async def get_document_content(document_id: str):
    """Get the full content of a document."""
    doc = get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "id": doc["id"],
        "filename": doc["filename"],
        "content": doc.get("content", ""),
        "summary": doc.get("summary", ""),
    }


@router.post("", response_model=DocumentResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    chat_id: Optional[str] = Form(None),
):
    """
    Upload a document for processing.

    Supported formats: PDF, PNG, JPG, GIF, TXT, MD
    PDFs and images are processed with VLM for OCR.
    """
    # Validate filename
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    if not is_allowed_file(file.filename):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Generate unique document ID and file path
    doc_id = str(uuid.uuid4())
    file_ext = get_file_extension(file.filename)
    safe_filename = f"{doc_id}{file_ext}"
    file_path = UPLOAD_DIR / safe_filename

    # Save file
    try:
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # Check file size (max 50MB)
        file_size = len(content)
        if file_size > 50 * 1024 * 1024:
            file_path.unlink()  # Cleanup
            raise HTTPException(status_code=400, detail="File too large. Maximum 50MB.")

    except Exception as e:
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # Create document record
    doc = create_document(
        chat_id=chat_id,
        filename=file.filename,
        file_type=file_ext[1:],  # Remove the dot
        file_path=str(file_path),
        metadata={"file_size": file_size}
    )

    # Schedule background processing
    background_tasks.add_task(
        process_document_file,
        doc_id,
        file_path,
        file.filename,
        chat_id
    )

    return DocumentResponse(
        id=doc["id"],
        filename=file.filename,
        file_type=file_ext[1:],
        summary=None,
        chunk_count=0,
        status="processing",
        created_at=datetime.now().isoformat(),
    )


@router.delete("/{document_id}")
async def delete_document(document_id: str):
    """Delete a document by ID and its associated memories."""
    # Get document to find file path
    doc = get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete file from disk
    file_path = doc.get("file_path")
    if file_path and Path(file_path).exists():
        try:
            Path(file_path).unlink()
        except Exception as e:
            logger.warning(f"Failed to delete file {file_path}: {e}")

    # Delete from vector memory (Qdrant)
    from tools.memory_tool import delete_document_memories
    memories_deleted = delete_document_memories(document_id)
    logger.info(f"Deleted {memories_deleted} associated memories from vector store")

    # Delete from database
    success = db_delete_document(document_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete document")

    return {"success": True}


@router.get("/search", response_model=SearchResponse)
async def search_documents_endpoint(
    q: str,
    chat_id: Optional[str] = None,
    limit: int = 10,
):
    """Full-text search across documents."""
    if not q or len(q.strip()) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")

    results = db_search_documents(query=q, chat_id=chat_id, limit=limit)

    return SearchResponse(
        results=results,
        total=len(results)
    )
