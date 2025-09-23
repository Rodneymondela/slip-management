import json
import pytest
from sliptrack.app import create_app
from sliptrack.blueprints.uploads.ocr_adapter import OcrAdapter

@pytest.fixture
def app():
    app = create_app()
    app.config.update({
        "TESTING": True,
    })
    yield app

def test_parse_grocery_text(app):
    with app.app_context():
        text = open('tests/fixtures/sample_texts/grocery.txt','r',encoding='utf-8').read()
        data = OcrAdapter().parse_fields(text)
        assert data['vat_rate'] == app.config['VAT_RATE']
        assert data['supplier_name'] is not None

def test_parse_invoice_text(app):
    with app.app_context():
        text = open('tests/fixtures/sample_texts/invoice.txt','r',encoding='utf-8').read()
        data = OcrAdapter().parse_fields(text)
        assert 'total_amount' in data

def test_parse_cash_sale_text(app):
    with app.app_context():
        text = open('tests/fixtures/sample_texts/cash_sale.txt','r',encoding='utf-8').read()
        data = OcrAdapter().parse_fields(text)
        assert 'payment_method' in data
