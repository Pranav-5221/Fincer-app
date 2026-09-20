"""
Fincer SMS Parser

Parses raw bank transaction SMS into structured data.

Responsibility:
    RAW SMS -> PARSED DATA

This module does NOT save anything to the database.
The API view handles authentication, validation, and saving.
"""

import re
from decimal import Decimal, InvalidOperation
from datetime import datetime

from .models import TransactionType, Category


# -- Amount --
#
# Supports: Rs.500, Rs 500, Rs. 500, INR 500,
#           Rs.1,500, Rs.1,500.00, INR 1,500.00

AMOUNT_PATTERN = re.compile(
    r'(?:Rs\.?\s*|INR\.?\s*|\u20b9\s*)([\d,]+(?:\.\d{1,2})?)',
    re.IGNORECASE,
)


def extract_amount(sms):
    """Extract transaction amount as Decimal. Returns None if not found."""
    match = AMOUNT_PATTERN.search(sms)
    if not match:
        return None
    raw = match.group(1).replace(',', '')
    if not raw:
        return None
    try:
        amount = Decimal(raw)
        if amount <= 0:
            return None
        return amount
    except InvalidOperation:
        return None


# -- Transaction Type --

EXPENSE_KEYWORDS = [
    'debited', 'debit', 'spent', 'withdrawn',
    'purchase', 'paid', 'payment',
]

INCOME_KEYWORDS = [
    'credited', 'credit', 'received', 'deposited',
]


def extract_transaction_type(sms):
    """Detect whether the SMS describes an expense or income."""
    lower = sms.lower()
    for keyword in EXPENSE_KEYWORDS:
        if keyword in lower:
            return TransactionType.EXPENSE
    for keyword in INCOME_KEYWORDS:
        if keyword in lower:
            return TransactionType.INCOME
    return None


# -- Bank Detection --
#
# Initial support: SBI, HDFC, ICICI, Axis
# Expandable later: Kotak, PNB, BOB, Yes Bank, etc.

BANK_PATTERNS = [
    (re.compile(r'\bSBI\b', re.IGNORECASE), 'SBI'),
    (re.compile(r'\bHDFC(?:\s?Bank|BK)?\b', re.IGNORECASE), 'HDFC'),
    (re.compile(r'\bICICI(?:\s?Bank)?\b', re.IGNORECASE), 'ICICI'),
    (re.compile(r'\bAxis(?:\s?Bank|BK)?\b', re.IGNORECASE), 'Axis'),
    (re.compile(r'\bKotak\b', re.IGNORECASE), 'Kotak'),
    (re.compile(r'\bPNB\b', re.IGNORECASE), 'PNB'),
    (re.compile(r'\b(?:Bank\s?of\s?Baroda|BOB)\b', re.IGNORECASE), 'Bank of Baroda'),
    (re.compile(r'\bYes\s?Bank\b', re.IGNORECASE), 'Yes Bank'),
    (re.compile(r'\bIndusInd\b', re.IGNORECASE), 'IndusInd'),
    (re.compile(r'\bCanara\b', re.IGNORECASE), 'Canara'),
    (re.compile(r'\bUnion\s?Bank\b', re.IGNORECASE), 'Union Bank'),
    (re.compile(r'\bIDBI\b', re.IGNORECASE), 'IDBI'),
    (re.compile(r'\bFederal\s?Bank\b', re.IGNORECASE), 'Federal Bank'),
]


def extract_bank(sms):
    """Identify the bank from the SMS text. Returns None if not found."""
    for pattern, bank_name in BANK_PATTERNS:
        if pattern.search(sms):
            return bank_name
    return None


# -- Merchant Extraction --
#
# Looks for merchant names after trigger words: at, to, towards
#
# "from" is intentionally excluded because it almost always
# appears as "from your account" which is not a merchant.
#
# "for" is excluded because it often precedes amounts like
# "for Rs.500".

MERCHANT_PATTERN = re.compile(
    r"\b(?:at|to|towards)\s+([A-Za-z][A-Za-z0-9\s&.'-]*)",
    re.IGNORECASE,
)

# Words that signal end of merchant name
MERCHANT_STOP_WORDS = {
    'on', 'at', 'from', 'your', 'a/c', 'account', 'ref',
    'upi', 'neft', 'imps', 'rtgs', 'the', 'for', 'via',
    'through', 'using', 'with', 'in', 'is', 'was', 'has',
    'been', 'and', 'or', 'of', 'not', 'no', 'avl', 'bal',
    'balance', 'available', 'transaction', 'txn',
}


def extract_merchant(sms):
    """
    Extract merchant name from the SMS.
    Returns None if merchant cannot be confidently determined.
    The parser should never invent data.
    """
    for match in MERCHANT_PATTERN.finditer(sms):
        raw = match.group(1).strip()
        words = raw.split()
        merchant_words = []
        for word in words:
            if word.lower().rstrip('.,;:') in MERCHANT_STOP_WORDS:
                break
            merchant_words.append(word)
        if merchant_words:
            merchant = ' '.join(merchant_words).strip(' .,;:')
            if merchant:
                return merchant
    return None


# -- Transaction Date/Time --
#
# Ordered from most specific to least specific to prevent
# partial matches (e.g. DD-MM-YYYY must be tried before
# DD-MM-YY to avoid matching first 6 digits of an 8-digit
# date).

DATE_PATTERNS = [
    # DD-MM-YYYY HH:MM:SS or HH:MM
    (
        re.compile(r'(\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2}(?::\d{2})?)'),
        ['%d-%m-%Y %H:%M:%S', '%d-%m-%Y %H:%M'],
    ),
    # DD/MM/YYYY HH:MM:SS or HH:MM
    (
        re.compile(r'(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}(?::\d{2})?)'),
        ['%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M'],
    ),
    # DD-MM-YYYY (must come before DD-MM-YY)
    (
        re.compile(r'(\d{2}-\d{2}-\d{4})'),
        ['%d-%m-%Y'],
    ),
    # DD/MM/YYYY
    (
        re.compile(r'(\d{2}/\d{2}/\d{4})'),
        ['%d/%m/%Y'],
    ),
    # DD-Mon-YYYY (e.g. 20-Sep-2026)
    (
        re.compile(r'(\d{2}-[A-Za-z]{3}-\d{4})'),
        ['%d-%b-%Y'],
    ),
    # DD-Mon-YY (e.g. 20-Sep-26)
    (
        re.compile(r'(\d{2}-[A-Za-z]{3}-\d{2})'),
        ['%d-%b-%y'],
    ),
    # DDMONYY (e.g. 24APR26, 20SEP26)
    (
        re.compile(r'(\d{2}[A-Z]{3}\d{2})', re.IGNORECASE),
        ['%d%b%y'],
    ),
    # DD-MM-YY (e.g. 20-09-26) -- checked after YYYY variants
    (
        re.compile(r'(\d{2}-\d{2}-\d{2})(?!\d)'),
        ['%d-%m-%y'],
    ),
    # DD/MM/YY
    (
        re.compile(r'(\d{2}/\d{2}/\d{2})(?!\d)'),
        ['%d/%m/%y'],
    ),
]


def extract_transaction_date(sms):
    """
    Extract transaction date/time from the SMS.
    Returns a datetime object or None.

    If the SMS does not contain a date, the API view should
    use the Flutter-provided received_at as a fallback.
    """
    for pattern, formats in DATE_PATTERNS:
        match = pattern.search(sms)
        if match:
            date_str = match.group(1)
            for fmt in formats:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
    return None


# -- Category Inference --
#
# Category is inferred, not a fact from the bank SMS.
# The user can correct it later via PATCH.

CATEGORY_MAP = {
    # FOOD
    'swiggy': Category.FOOD,
    'zomato': Category.FOOD,
    'dominos': Category.FOOD,
    'mcdonald': Category.FOOD,
    'starbucks': Category.FOOD,
    'pizza hut': Category.FOOD,
    'burger king': Category.FOOD,
    'kfc': Category.FOOD,
    'dunkin': Category.FOOD,
    'barbeque nation': Category.FOOD,

    # SHOPPING
    'amazon': Category.SHOPPING,
    'flipkart': Category.SHOPPING,
    'myntra': Category.SHOPPING,
    'ajio': Category.SHOPPING,
    'nykaa': Category.SHOPPING,
    'meesho': Category.SHOPPING,
    'croma': Category.SHOPPING,
    'reliance': Category.SHOPPING,
    'bigbasket': Category.SHOPPING,
    'dmart': Category.SHOPPING,

    # TRAVEL
    'uber': Category.TRAVEL,
    'ola': Category.TRAVEL,
    'rapido': Category.TRAVEL,
    'irctc': Category.TRAVEL,
    'makemytrip': Category.TRAVEL,
    'cleartrip': Category.TRAVEL,
    'goibibo': Category.TRAVEL,
    'redbus': Category.TRAVEL,
    'yatra': Category.TRAVEL,
}


def infer_category(merchant):
    """
    Infer transaction category from the merchant name.
    Returns Category.OTHER if the merchant is unknown.
    """
    if not merchant:
        return Category.OTHER
    lower = merchant.lower()
    for keyword, category in CATEGORY_MAP.items():
        if keyword in lower:
            return category
    return Category.OTHER


# -- Main Parser --


def parse_sms(sms_text):
    """
    Parse a raw bank transaction SMS into structured data.

    Input:
        sms_text -- raw SMS string

    Output on success:
        {
            "amount": Decimal("500.00"),
            "transaction_type": 1,
            "bank": "SBI",
            "merchant": "Swiggy" or None,
            "category": 1,
            "transaction_at": datetime or None,
        }

    Output on failure:
        None

    Required fields (parse fails if any is missing):
        amount, transaction_type, bank

    Optional fields:
        merchant (can be None)
        category (defaults to OTHER)
        transaction_at (can be None -- view uses fallback)
    """
    if not sms_text or not isinstance(sms_text, str):
        return None

    amount = extract_amount(sms_text)
    if amount is None:
        return None

    transaction_type = extract_transaction_type(sms_text)
    if transaction_type is None:
        return None

    bank = extract_bank(sms_text)
    if bank is None:
        return None

    merchant = extract_merchant(sms_text)
    category = infer_category(merchant)
    transaction_at = extract_transaction_date(sms_text)

    return {
        "amount": amount,
        "transaction_type": transaction_type,
        "bank": bank,
        "merchant": merchant,
        "category": category,
        "transaction_at": transaction_at,
    }
