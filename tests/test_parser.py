import json
from sliptrack.blueprints.uploads.ocr_adapter import OcrAdapter

def test_parse_grocery_text():
    text = open('tests/fixtures/sample_texts/grocery.txt','r',encoding='utf-8').read()
    data = OcrAdapter().parse_fields(text)
    assert data['vat_rate'] == 0.15
    assert data['supplier_name'] is not None

def test_parse_invoice_text():
    text = open('tests/fixtures/sample_texts/invoice.txt','r',encoding='utf-8').read()
    data = OcrAdapter().parse_fields(text)
    assert 'total_amount' in data

def test_parse_cash_sale_text():
    text = open('tests/fixtures/sample_texts/cash_sale.txt','r',encoding='utf-8').read()
    data = OcrAdapter().parse_fields(text)
    assert 'payment_method' in data
