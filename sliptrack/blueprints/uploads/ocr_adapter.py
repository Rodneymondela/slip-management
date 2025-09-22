import re
import pytesseract
from .image_utils import preprocess_for_ocr
from datetime import datetime
from decimal import Decimal

class OcrAdapter:
    VAT_RATE = Decimal('0.15')

    def preprocess(self, image_path):
        return preprocess_for_ocr(image_path)

    def extract_text(self, preprocessed_image):
        return pytesseract.image_to_string(preprocessed_image)

    def parse_fields(self, raw_text: str, supplier_hint: str|None=None) -> dict:
        text = raw_text.replace('\r','').strip()
        # Supplier heuristic: first non-empty line
        supplier_name = None
        for line in text.splitlines():
            line=line.strip()
            if line:
                supplier_name = line[:128]
                break

        # Date finders
        date = None
        patterns = [
            r"\b\d{4}-\d{2}-\d{2}\b",
            r"\b\d{2}/\d{2}/\d{4}\b",
            r"\b\d{1,2}\s(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s\d{4}\b",
        ]
        for p in patterns:
            m = re.search(p, text, flags=re.I)
            if m:
                date = self._normalize_date(m.group(0))
                break

        # Reference
        ref = None
        m = re.search(r"(Invoice\s*No\.?|Inv\s*#|Receipt\s*#|Till\s*No|Txn\s*#)[:\-]?\s*([\w/-]+)", text, flags=re.I)
        if m:
            ref = m.group(2)[:64]

        # Amounts near keywords
        def find_amount(keyword):
            pat = rf"{keyword}[^\d]*(R\s*)?([0-9]+(?:[\.,][0-9]{{2}})?)"
            m = re.search(pat, text, flags=re.I)
            if m:
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
            subtotal = (total / (Decimal('1.00') + self.VAT_RATE)).quantize(Decimal('0.01'))
            vat = (total - subtotal).quantize(Decimal('0.01'))

        # Payment method
        payment = 'unknown'
        if re.search(r"CARD|MASTERCARD|VISA|DEBIT", text, flags=re.I):
            payment = 'card'
        elif re.search(r"EFT", text, flags=re.I):
            payment = 'eft'
        elif re.search(r"CASH", text, flags=re.I):
            payment = 'cash'

        return {
            "supplier_name": supplier_name,
            "supplier_vat_number": None,
            "entry_date": date,
            "reference_no": ref,
            "subtotal": float(subtotal) if subtotal is not None else None,
            "vat_rate": float(self.VAT_RATE),
            "vat_amount": float(vat) if vat is not None else None,
            "total_amount": float(total) if total is not None else None,
            "payment_method": payment,
            "category": None,
            "notes": "OCR auto"
        }

    def _normalize_date(self, s: str) -> str|None:
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d %b %Y"):
            try:
                d = datetime.strptime(s, fmt).date()
                return d.isoformat()
            except Exception:
                continue
        return None
