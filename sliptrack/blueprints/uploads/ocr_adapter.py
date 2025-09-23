import logging
import re
import pytesseract
from flask import current_app
from .image_utils import preprocess_for_ocr
from datetime import datetime
from decimal import Decimal
from dateutil.parser import parse as parse_date

class OcrAdapter:
    def __init__(self):
        self.vat_rate = Decimal(str(current_app.config.get('VAT_RATE', '0.15')))

    def preprocess(self, image_path):
        return preprocess_for_ocr(image_path)

    def extract_text(self, preprocessed_image):
        return pytesseract.image_to_string(preprocessed_image)

    def parse_fields(self, raw_text: str, supplier_hint: str|None=None) -> dict:
        text = raw_text.replace('\r','').strip()
        # Supplier heuristic
        supplier_name = self._find_supplier(text, supplier_hint)

        # Date finders
        date = self._find_date(text)

        # Reference
        ref = None
        m = re.search(r"(Invoice\s*No\.?|Inv\s*#|Receipt\s*#|Till\s*No|Txn\s*#)[:\-]?\s*([\w/-]+)", text, flags=re.I)
        if m:
            ref = m.group(2)[:64]

        # Amounts near keywords
        def find_amount(keyword):
            pat = rf"{keyword}[^\d]*(R\s*)?([0-9]+(?:[.,][0-9]{2})?)"
            m = re.search(pat, text, flags=re.I)
            if m and m.group(2):
                amt = m.group(2).replace(',', '.')
                try:
                    return Decimal(amt)
                except Exception:
                    return None
            return None

        total = find_amount("TOTAL|AMOUNT DUE|AMT DUE")
        subtotal = find_amount("SUBTOTAL|SUB-TOTAL")
        vat = find_amount("VAT|TAX")

        # VAT included inference
        vat_included = bool(re.search(r"VAT\s*(incl|included)", text, flags=re.I))
        if total is not None and vat is None and subtotal is None and vat_included:
            subtotal = (total / (Decimal('1.00') + self.vat_rate)).quantize(Decimal('0.01'))
            vat = (total - subtotal).quantize(Decimal('0.01'))

        # Payment method
        payment = 'unknown'
        if re.search(r"CARD|MASTERCARD|VISA|DEBIT", text, flags=re.I):
            payment = 'card'
        elif re.search(r"EFT", text, flags=re.I):
            payment = 'eft'
        elif re.search(r"CASH", text, flags=re.I):
            payment = 'cash'

        result = {
            "supplier_name": supplier_name,
            "supplier_vat_number": None,
            "entry_date": date,
            "reference_no": ref,
            "subtotal": float(subtotal) if subtotal is not None else None,
            "vat_rate": float(self.vat_rate),
            "vat_amount": float(vat) if vat is not None else None,
            "total_amount": float(total) if total is not None else None,
            "payment_method": payment,
            "category": None,
            "notes": "OCR auto"
        }
        logging.info(f"OCR raw text:\n{raw_text}")
        logging.info(f"Parsed fields: {result}")
        return result

    def _find_date(self, text: str) -> str | None:
        patterns = [
            r"\b\d{4}-\d{2}-\d{2}\b",
            r"\b\d{2}/\d{2}/\d{4}\b",
            r"\b\d{1,2}\s(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-zA-Z,.]*\s\d{4}\b",
        ]
        for p in patterns:
            m = re.search(p, text, flags=re.I)
            if m:
                try:
                    return parse_date(m.group(0)).date().isoformat()
                except (ValueError, TypeError):
                    continue
        return None

    def _find_supplier(self, text: str, hint: str | None = None) -> str | None:
        if hint:
            return hint

        # Heuristic: Find line with VAT registration number, assume supplier name is on the same or previous line
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if re.search(r'VAT\s*Reg\s*No', line, re.I):
                # Check current line, then previous line
                if len(line.strip()) > 15 and i > 0:
                    return lines[i-1].strip()[:128]
                elif len(line.strip()) > 15:
                    return line.strip()[:128]

        # Fallback to first non-empty line
        for line in lines:
            line = line.strip()
            if line:
                return line[:128]
        return None
