import os
import re
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List
from dateutil import parser as date_parser

import cv2
import numpy as np
import pytesseract


class OcrAdapter:
    """
    Tesseract OCR with stronger preprocessing and confidence-filtered text.
    Fallbacks ensure we always return something usable.
    """

    def __init__(self) -> None:
        # Language(s). You can set TESS_LANG=eng+afr in .env if helpful.
        self.lang = os.getenv("TESS_LANG", "eng")

        # Allow tweaking confidence gate from .env; default 55 (was 65)
        try:
            self.min_conf = int(os.getenv("OCR_MIN_CONF", "55"))
        except Exception:
            self.min_conf = 55

    # ---------- preprocessing ----------

    def _read_image(self, path: str) -> np.ndarray:
        img = cv2.imread(path)
        if img is None:
            raise ValueError(f"Could not read image: {path}")
        return img

    @staticmethod
    def _to_gray(img: np.ndarray) -> np.ndarray:
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    @staticmethod
    def _denoise(gray: np.ndarray) -> np.ndarray:
        return cv2.fastNlMeansDenoising(gray, None, h=10, templateWindowSize=7, searchWindowSize=21)

    @staticmethod
    def _deskew(gray: np.ndarray) -> np.ndarray:
        thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        coords = np.column_stack(np.where(thr == 0))
        if coords.size == 0:
            return gray
        angle = cv2.minAreaRect(coords)[-1]
        angle = -(90 + angle) if angle < -45 else -angle
        (h, w) = gray.shape[:2]
        M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
        return cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

    @staticmethod
    def _clahe(gray: np.ndarray) -> np.ndarray:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return clahe.apply(gray)

    @staticmethod
    def _adaptive(gray: np.ndarray) -> np.ndarray:
        return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY, 31, 15)

    @staticmethod
    def _scale(gray: np.ndarray, factor: float) -> np.ndarray:
        h, w = gray.shape
        return cv2.resize(gray, (int(w * factor), int(h * factor)), interpolation=cv2.INTER_CUBIC)

    def preprocess(self, image_path: str) -> np.ndarray:
        gray = self._to_gray(self._read_image(image_path))
        den = self._denoise(gray)
        desk = self._deskew(den)
        cla = self._clahe(desk)
        th = self._adaptive(cla)
        return th

    # ---------- OCR ----------

    def extract_text(self, image_or_path) -> str:
        """
        Extracts text from a preprocessed image array or an image path.
        This simplified method uses a single, robust Tesseract configuration for speed.
        """
        # If a path is provided, preprocess it. Otherwise, assume it's a preprocessed numpy array.
        if isinstance(image_or_path, str):
            try:
                processed_img = self.preprocess(image_or_path)
            except ValueError:
                # Could not read image, etc.
                return ""
        else:
            processed_img = image_or_path

        # Use a reliable Page Segmentation Mode for receipts/invoices.
        # PSM 4: Assume a single column of text of variable sizes. Good general default.
        config = "--oem 3 --psm 4"

        try:
            text = pytesseract.image_to_string(
                processed_img, lang=self.lang, config=config
            ).strip()

            # If text is very short, it might be noise. A fallback can be useful.
            if len(text) < 20:
                # PSM 6 is another common choice for blocks of text.
                config_fallback = "--oem 3 --psm 6"
                fallback_text = pytesseract.image_to_string(
                    processed_img, lang=self.lang, config=config_fallback
                ).strip()
                if len(fallback_text) > len(text):
                    return fallback_text
            return text
        except Exception:
            # If any Tesseract error occurs, return an empty string.
            return ""

    # ---------- parsing ----------

    def parse_fields(self, raw_text: str) -> Dict[str, Any]:
        text = (raw_text or "").replace("\x0c", " ")
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        joined = "\n".join(lines)
        lowered = joined.lower()

        # Supplier from top lines with decent letter ratio
        supplier = ""
        def clean(s: str) -> str:
            s = re.sub(r"[^A-Za-z0-9&\.\-\'\s]", " ", s)
            s = re.sub(r"\s{2,}", " ", s).strip(" -'")
            return s
        def letter_ratio(s: str) -> float:
            letters = sum(ch.isalpha() for ch in s)
            return letters / max(1, len(s))

        for ln in lines[:10]:
            if re.search(r"(tax|vat|invoice|receipt|till|cash|total|amount due)", ln, re.I):
                continue
            cand = clean(ln)
            if len(cand) >= 3 and letter_ratio(cand) >= 0.40:
                supplier = cand
                break

        # Date
        entry_date: Optional[str] = None
        try:
            # Use a regex to find plausible date-like strings first
            # This avoids dateutil trying to parse random numbers
            date_pattern = r"\b(\d{1,4}[-/. ]\d{1,2}[-/. ]\d{1,4}|\d{1,2}\s+[A-Za-z]{3,}\s+\d{2,4})\b"
            matches = re.findall(date_pattern, joined)
            for match in matches:
                try:
                    # dayfirst=True is a safe bet for many receipts
                    parsed_date = date_parser.parse(match, dayfirst=True).date()
                    entry_date = parsed_date.isoformat()
                    break  # Stop after the first successful parse
                except (date_parser.ParserError, TypeError, ValueError):
                    continue
        except Exception:
            pass  # Ignore if regex or parsing fails entirely
        if not entry_date:
            entry_date = datetime.today().date().isoformat()

        # A more robust regex for monetary values that handles thousands separators
        money_pattern = r"\b\d{1,3}(?:[.,]\d{3})*[.,]\d{2}\b"

        # Totals (prefer explicit lines)
        total = None
        for ln in reversed(lines):
            if re.search(r"(total|amount\s*due|grand\s*total)", ln, re.I):
                m = re.findall(money_pattern, ln)
                if m:
                    total = self._num(m[-1])
                    break
        if total is None:
            m = re.findall(money_pattern, joined)
            if m:
                # Fallback to the largest monetary value in the text
                all_nums = sorted([self._num(v) for v in m if self._num(v) is not None], reverse=True)
                if all_nums:
                    total = all_nums[0]

        vat_amount = None
        for ln in lines:
            # Avoid matching the total amount again if it's on the same line as "VAT"
            if re.search(r"\b(vat|tax)\b", ln, re.I) and not re.search(r"total", ln, re.I):
                m = re.findall(money_pattern, ln)
                if m:
                    vat_amount = self._num(m[-1])

        subtotal = None
        for ln in lines:
            if re.search(r"(subtotal|sub\s*total)", ln, re.I):
                m = re.findall(money_pattern, ln)
                if m:
                    subtotal = self._num(m[-1])

        vat_rate = 0.15  # ZA default

        # Supplier VAT number – prefer lines mentioning VAT
        supplier_vat = ""
        for ln in lines:
            if re.search(r"\bvat\b", ln, re.I):
                m = re.search(r"(\d{10})", re.sub(r"\s", "", ln))
                if m:
                    supplier_vat = m.group(1); break
        if not supplier_vat:
            m = re.search(r"(\d{10})", re.sub(r"\s", "", joined))
            supplier_vat = m.group(1) if m else ""

        # Reference
        ref = ""
        # Search line-by-line to avoid incorrect cross-line matches.
        # The pattern looks for common invoice/receipt keywords.
        pattern = r"(invoice|receipt|till|order|statement)\s*(no|#|num|number)?\s*[:\-#]?\s*([A-Za-z0-9\-/]+)"
        for ln in lines:
            m = re.search(pattern, ln, re.I)
            if m:
                # Group 3 should contain the reference number.
                candidate = m.group(3)
                # A sanity check to avoid using common keywords like 'No' as the reference.
                if candidate and candidate.lower() not in ['no', 'num', 'number']:
                    ref = candidate
                    break  # Found a good candidate, stop searching.

        # Derive if only total present and VAT included
        if total is not None and vat_amount is None and subtotal is None:
            base = total / (1 + vat_rate)
            subtotal = round(base, 2)
            vat_amount = round(total - base, 2)

        return {
            "supplier_name": supplier,
            "supplier_vat_number": supplier_vat,
            "entry_date": entry_date,
            "reference_no": ref,
            "subtotal": subtotal,
            "vat_rate": vat_rate,
            "vat_amount": vat_amount,
            "total_amount": total,
            "payment_method": "unknown",
            "category": "",
            "notes": "OCR auto" if text else "Manual entry",
        }

    @staticmethod
    def _num(s: str) -> Optional[float]:
        """
        Robustly converts a string to a float, handling common European and
        American-style number formats with thousands separators.
        """
        if not s or not isinstance(s, str):
            return None

        s = s.strip()
        # Find the last dot or comma, which is the most likely decimal separator
        last_dot = s.rfind('.')
        last_comma = s.rfind(',')

        # If a comma appears after the last dot, it's likely a European-style number (e.g., 1.234,56)
        if last_comma > last_dot:
            # Remove all dots (thousands separators) and replace the comma with a dot (decimal separator)
            s = s.replace('.', '').replace(',', '.')
        else:
            # Otherwise, it's likely an American-style number (e.g., 1,234.56).
            # Just remove all commas (thousands separators).
            s = s.replace(',', '')

        try:
            return float(s)
        except (ValueError, TypeError):
            return None
