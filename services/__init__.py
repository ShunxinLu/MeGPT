"""
Services - Business logic services for MeGPT.

Contains:
- EmailProcessor: AI-powered email classification and processing
- EmailSyncService: Background email synchronization
"""

from services.email_processor import EmailProcessor, ProcessedEmail
from services.email_sync_service import EmailSyncService, get_sync_service

__all__ = [
    "EmailProcessor",
    "ProcessedEmail",
    "EmailSyncService",
    "get_sync_service",
]
