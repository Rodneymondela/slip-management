import os
import logging
import cv2
import numpy as np
from pdf2image import convert_from_path
from flask import current_app

from .extensions import celery_app, db
from .models.document import Document
from .blueprints.uploads.ocr_adapter import OcrAdapter

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="tasks.process_ocr", max_retries=1)
def process_ocr(self, document_id: int):
    """
    Celery task to perform OCR on a document. It handles both PDF and image files,
    applies preprocessing, and updates the document status in the database.
    """
    doc = Document.query.get(document_id)
    if not doc:
        logger.error(f"Document with ID {document_id} not found.")
        return

    # Construct the absolute path to the file in the instance folder
    absolute_file_path = os.path.join(current_app.instance_path, doc.file_path)
    logger.info(f"Starting OCR for document ID {doc.id} at path: {absolute_file_path}")

    try:
        self.update_state(state="PROGRESS", meta={"status": "Starting OCR..."})
        adapter = OcrAdapter()
        raw_text = ""

        if not os.path.exists(absolute_file_path):
            raise FileNotFoundError(f"File not found at path: {absolute_file_path}")

        _, ext = os.path.splitext(doc.file_path)
        if ext.lower() == ".pdf":
            self.update_state(state="PROGRESS", meta={"status": "Converting PDF..."})

            # Use POPPLER_PATH from environment if available
            poppler_path = os.getenv("POPPLER_PATH")
            images = convert_from_path(absolute_file_path, poppler_path=poppler_path, fmt='jpeg')

            all_texts = []
            for i, page_image in enumerate(images):
                self.update_state(
                    state="PROGRESS",
                    meta={"status": f"Processing page {i+1}/{len(images)}"},
                )
                # Convert PIL image to OpenCV format (BGR)
                img_cv = cv2.cvtColor(np.array(page_image), cv2.COLOR_RGB2BGR)

                # Use the centralized preprocessing method
                preprocessed_img = adapter.preprocess_image(img_cv)
                page_text = adapter.extract_text(preprocessed_img)
                all_texts.append(page_text)

            raw_text = "\n\n--- Page Break ---\n\n".join(all_texts)
        else:
            self.update_state(state="PROGRESS", meta={"status": "Preprocessing image..."})
            preprocessed_image = adapter.preprocess(absolute_file_path)

            self.update_state(state="PROGRESS", meta={"status": "Extracting text..."})
            raw_text = adapter.extract_text(preprocessed_image)

        doc.ocr_text = raw_text
        # If text is empty, it's a failure; otherwise, it needs human review.
        doc.status = "needs_review" if raw_text else "ocr_failed"
        doc.task_id = None # Clear task ID on successful completion
        db.session.commit()

        logger.info(f"OCR completed for document {doc.id}. Text length: {len(raw_text)}.")
        return {"status": "Completed", "ocr_text_length": len(raw_text)}

    except Exception as e:
        logger.exception(
            f"OCR task failed for document {doc.id}. Error: {e}",
            exc_info=True,
        )
        db.session.rollback()
        doc = Document.query.get(document_id) # Re-fetch doc in case session is expired
        if doc:
            doc.status = "ocr_failed"
            # Keep task_id for debugging purposes on failure
            db.session.commit()

        # Propagate exception to let Celery handle retries and record the failure
        raise e