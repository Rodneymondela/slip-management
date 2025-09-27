import os
import cv2
import numpy as np
from pdf2image import convert_from_path

# Import the shared Celery app and db instance from the extensions module
from .extensions import celery_app, db
from .models.document import Document
from .blueprints.uploads.ocr_adapter import OcrAdapter


@celery_app.task(bind=True, name="tasks.process_ocr")
def process_ocr(self, document_id: int):
    """
    Celery task to perform OCR on a document.
    The Flask app context is now handled automatically by the configuration in app.py.
    """
    try:
        # We can now safely access the database as the task runs within the app context
        doc = Document.query.get(document_id)
        if not doc:
            self.update_state(state='FAILURE', meta={'exc_type': 'NotFound', 'exc_message': f'Document {document_id} not found.'})
            return

        self.update_state(state='PROGRESS', meta={'status': 'Starting OCR...'})

        adapter = OcrAdapter()
        file_path = doc.file_path
        raw_text = ""

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found at path: {file_path}")

        _, ext = os.path.splitext(file_path)
        if ext.lower() == ".pdf":
            self.update_state(state='PROGRESS', meta={'status': 'Converting PDF...'})
            try:
                poppler_path = os.getenv("POPPLER_PATH")
                images = convert_from_path(file_path, poppler_path=poppler_path)
            except Exception as e:
                raise ValueError(f"PDF conversion failed. Is poppler-utils installed? Details: {e}")

            all_texts = []
            num_pages = len(images)
            for i, page_image in enumerate(images):
                self.update_state(state='PROGRESS', meta={'status': f'Processing page {i+1}/{num_pages}'})

                img_cv = cv2.cvtColor(np.array(page_image), cv2.COLOR_RGB2BGR)

                # Replicate the adapter's preprocessing pipeline for the in-memory image
                gray = OcrAdapter._to_gray(img_cv)
                den = OcrAdapter._denoise(gray)
                desk = OcrAdapter._deskew(den)
                cla = OcrAdapter._clahe(desk)
                th = OcrAdapter._adaptive(cla)

                page_text = adapter.extract_text(th)
                all_texts.append(page_text)

            raw_text = "\n\n--- Page Break ---\n\n".join(all_texts)
        else:
            self.update_state(state='PROGRESS', meta={'status': 'Preprocessing image...'})
            preprocessed_image = adapter.preprocess(file_path)
            self.update_state(state='PROGRESS', meta={'status': 'Extracting text...'})
            raw_text = adapter.extract_text(preprocessed_image)

        doc.ocr_text = raw_text
        doc.status = "parsed" if raw_text else "ocr_failed"
        doc.task_id = None  # Clear the task ID once complete
        db.session.commit()

        return {'status': 'Completed', 'ocr_text_length': len(raw_text)}

    except Exception as e:
        db.session.rollback()
        # The app context is available, so we can still query the DB
        doc = Document.query.get(document_id)
        if doc:
            doc.status = "ocr_failed"
            doc.task_id = None
            db.session.commit()

        self.update_state(state='FAILURE', meta={'exc_type': type(e).__name__, 'exc_message': str(e)})
        raise e