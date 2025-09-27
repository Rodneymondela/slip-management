import os
import re
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List

import cv2
import numpy as np
import pytesseract


class OcrAdapter:
    """
    Tesseract OCR with stronger preprocessing and confidence-filtered text.
    Fallbacks ensure we always return something usable.
    """

    def __init__(self) -> None:
        # Point pytesseract to exe via .env or common Windows paths
        cmd = os.getenv("TESSERACT_CMD")
        candidates: List[str] = []
        if cmd:
            candidates.append(cmd)
        if os.name == "nt":
            candidates += [
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            ]
        for c in candidates:
            if c and os.path.exists(c):
                pytesseract.pytesseract.tesseract_cmd = c
                break

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

    # ---------- OCR + scoring ----------

    def _ocr_data(self, img: np.ndarray, config: str):
        return pytesseract.image_to_data(
            img, lang=self.lang, config=config, output_type=pytesseract.Output.DICT
        )

    @staticmethod
    def _avg_conf(data) -> float:
        confs = [int(c) for c in data["conf"] if c != "-1"]
        return (sum(confs) / len(confs)) if confs else 0.0

    def _reconstruct_lines(self, data, min_conf: int) -> List[str]:
        lines: Dict[tuple, List[str]] = {}
        n = len(data["text"])
        for i in range(n):
            if data["text"][i] and data["text"][i].strip() and data["conf"][i] != "-1":
                c = int(data["conf"][i])
                if c >= min_conf:
                    key = (data["page_num"][i], data["block_num"][i], data["par_num"][i], data["line_num"][i])
                    lines.setdefault(key, []).append(data["text"][i])
        ordered = sorted(lines.items(), key=lambda kv: kv[0])
        return [" ".join(words) for _, words in ordered]

    def extract_text(self, image_or_path) -> str:
        # Accept path or preprocessed array
        base = self.preprocess(image_or_path) if isinstance(image_or_path, str) else image_or_path

        variants = [
            base,
            self._adaptive(self._clahe(base)),
            self._adaptive(self._scale(base, 1.7)),
            self._adaptive(self._scale(base, 1.3)),
        ]
        cfgs = ["--oem 1 --psm 6", "--oem 1 --psm 4", "--oem 1 --psm 7", "--oem 1 --psm 11"]

        best = {"score": -1.0, "data": None, "cfg": None}
        for im in variants:
            for cfg in cfgs:
                try:
                    data = self._ocr_data(im, cfg)
                    score = self._avg_conf(data)
                    if score > best["score"]:
                        best = {"score": score, "data": data, "cfg": cfg}
                except Exception:
                    continue

        # Build filtered text; if too short, fall back to full strings
        if best["data"]:
            filtered_lines = self._reconstruct_lines(best["data"], self.min_conf)
            filtered_text = "\n".join(filtered_lines).strip()
            if len(filtered_text) >= 20:  # good enough
                return filtered_text

        # Strong fallback: run full image_to_string on best variant with common PSMs
        for cfg in ("--oem 1 --psm 6", "--oem 1 --psm 4"):
            try:
                t = pytesseract.image_to_string(base, lang=self.lang, config=cfg).strip()
                if len(t) >= 10:
                    return t
            except Exception:
                pass

        return ""  # last resort

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
        for pat in (r"(\d{4}[-/]\d{2}[-/]\d{2})",
                    r"(\d{2}[-/]\d{2}[-/]\d{4})",
                    r"(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})"):
            m = re.search(pat, joined)
            if m:
                raw_d = m.group(1)
                for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y", "%d %b %Y"):
                    try:
                        entry_date = datetime.strptime(raw_d, fmt).date().isoformat()
                        break
                    except Exception:
                        pass
                if entry_date:
                    break
        if not entry_date:
            entry_date = datetime.today().date().isoformat()

        # Totals (prefer explicit lines)
        total = None
        for ln in reversed(lines):
            if re.search(r"(total|amount\s*due|grand\s*total)", ln, re.I):
                m = re.findall(r"([0-9]+[\.,][0-9]{2})", ln)
                if m:
                    total = self._num(m[-1]); break
        if total is None:
            m = re.findall(r"([0-9]+[\.,][0-9]{2})", joined)
            if m:
                total = self._num(m[-1])

        vat_amount = None
        for ln in lines:
            if re.search(r"\b(vat|tax)\b", ln, re.I):
                m = re.findall(r"([0-9]+[\.,][0-9]{2})", ln)
                if m:
                    vat_amount = self._num(m[-1])

        subtotal = None
        for ln in lines:
            if re.search(r"(subtotal|sub\s*total)", ln, re.I):
                m = re.findall(r"([0-9]+[\.,][0-9]{2})", ln)
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
        m = re.search(r"(invoice|receipt|till)\s*(no|#|num|number)?\s*[:\-]?\s*([A-Za-z0-9\-\/]+)", joined, re.I)
        if m:
            ref = m.group(3)

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
        try:
            return float(s.replace(",", "."))
        except Exception:
            return None
