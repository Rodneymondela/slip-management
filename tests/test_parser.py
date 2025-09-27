from sliptrack.blueprints.uploads.ocr_adapter import OcrAdapter

def test_parse_grocery_text(app):
    """
    Tests parsing of a typical grocery store receipt.
    Focuses on identifying the supplier and extracting the total amount.
    """
    with app.app_context():
        text = open('tests/fixtures/sample_texts/grocery.txt', 'r', encoding='utf-8').read()
        adapter = OcrAdapter()
        data = adapter.parse_fields(text)

        assert data['supplier_name'] == "CHECKERS HYPER"
        assert data['total_amount'] == 100.00
        assert data['entry_date'] == "2025-09-12"

def test_parse_invoice_text(app):
    """
    Tests parsing of a standard tax invoice.
    Focuses on extracting VAT, subtotal, and invoice number.
    """
    with app.app_context():
        text = open('tests/fixtures/sample_texts/invoice.txt', 'r', encoding='utf-8').read()
        adapter = OcrAdapter()
        data = adapter.parse_fields(text)

        assert data['supplier_name'] == "Acme Services Pty Ltd"
        assert data['total_amount'] == 2300.00
        assert data['subtotal'] == 2000.00
        assert data['vat_amount'] == 300.00
        assert data['reference_no'] == "INV-2025-001"

def test_parse_cash_sale_text(app):
    """
    Tests parsing of a simple cash sale slip.
    Focuses on identifying the supplier and total, even with less structure.
    """
    with app.app_context():
        text = open('tests/fixtures/sample_texts/cash_sale.txt', 'r', encoding='utf-8').read()
        adapter = OcrAdapter()
        data = adapter.parse_fields(text)

        assert data['supplier_name'] == "SHOPRITE"
        assert data['total_amount'] == 57.50
        assert data['entry_date'] == "2025-09-01"