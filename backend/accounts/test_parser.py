"""
Unit tests for the Fincer SMS Parser.

Tests cover:
- Expense and income SMS
- ₹, Rs, INR amount formats
- Comma-separated and decimal amounts
- Bank detection (SBI, HDFC, ICICI, Axis, etc.)
- Merchant present and absent
- Date formats (DD-MM-YY, DD-MM-YYYY, DDMONYY, etc.)
- Category inference
- Invalid / non-transaction SMS
- Missing required fields
"""

from decimal import Decimal
from datetime import datetime

from django.test import TestCase

from accounts.parser import (
    parse_sms,
    extract_amount,
    extract_transaction_type,
    extract_bank,
    extract_merchant,
    extract_transaction_date,
    infer_category,
)
from accounts.models import TransactionType, Category


# ── Amount Extraction ───────────────────────────────────────


class TestExtractAmount(TestCase):

    def test_rs_dot_amount(self):
        self.assertEqual(extract_amount("Rs.500 debited"), Decimal("500"))

    def test_rs_space_amount(self):
        self.assertEqual(extract_amount("Rs 500 debited"), Decimal("500"))

    def test_rs_dot_space_amount(self):
        self.assertEqual(extract_amount("Rs. 500 debited"), Decimal("500"))

    def test_inr_amount(self):
        self.assertEqual(extract_amount("INR 500 debited"), Decimal("500"))

    def test_rupee_symbol(self):
        self.assertEqual(extract_amount("₹500 debited"), Decimal("500"))

    def test_comma_separated(self):
        self.assertEqual(extract_amount("Rs.1,500 debited"), Decimal("1500"))

    def test_comma_separated_with_decimal(self):
        self.assertEqual(
            extract_amount("₹1,500.50 debited"),
            Decimal("1500.50"),
        )

    def test_large_amount(self):
        self.assertEqual(
            extract_amount("INR 25,00,000.00 credited"),
            Decimal("2500000.00"),
        )

    def test_no_amount(self):
        self.assertIsNone(extract_amount("Your account has been updated"))

    def test_decimal_amount(self):
        self.assertEqual(extract_amount("Rs.499.99 spent"), Decimal("499.99"))


# ── Transaction Type ────────────────────────────────────────


class TestExtractTransactionType(TestCase):

    def test_debited(self):
        self.assertEqual(
            extract_transaction_type("Rs.500 debited from account"),
            TransactionType.EXPENSE,
        )

    def test_spent(self):
        self.assertEqual(
            extract_transaction_type("Rs.500 spent at Swiggy"),
            TransactionType.EXPENSE,
        )

    def test_credited(self):
        self.assertEqual(
            extract_transaction_type("Rs.5000 credited to your account"),
            TransactionType.INCOME,
        )

    def test_received(self):
        self.assertEqual(
            extract_transaction_type("Rs.5000 received from UPI"),
            TransactionType.INCOME,
        )

    def test_purchase(self):
        self.assertEqual(
            extract_transaction_type("Purchase of Rs.500"),
            TransactionType.EXPENSE,
        )

    def test_unknown_type(self):
        self.assertIsNone(
            extract_transaction_type("Your account balance is Rs.5000")
        )


# ── Bank Detection ──────────────────────────────────────────


class TestExtractBank(TestCase):

    def test_sbi(self):
        self.assertEqual(extract_bank("debited from SBI account"), "SBI")

    def test_hdfc(self):
        self.assertEqual(extract_bank("HDFC Bank account debited"), "HDFC")

    def test_hdfcbk(self):
        self.assertEqual(extract_bank("HDFCBK: Rs.500 debited"), "HDFC")

    def test_icici(self):
        self.assertEqual(extract_bank("ICICI Bank alert"), "ICICI")

    def test_axis(self):
        self.assertEqual(extract_bank("Axis Bank debit"), "Axis")

    def test_kotak(self):
        self.assertEqual(extract_bank("Kotak account debited"), "Kotak")

    def test_unknown_bank(self):
        self.assertIsNone(extract_bank("Rs.500 debited from your account"))

    def test_case_insensitive(self):
        self.assertEqual(extract_bank("sbi account debited"), "SBI")


# ── Merchant Extraction ────────────────────────────────────


class TestExtractMerchant(TestCase):

    def test_at_merchant(self):
        self.assertEqual(
            extract_merchant("Rs.500 debited at Swiggy on 20-09-26"),
            "Swiggy",
        )

    def test_to_merchant(self):
        self.assertEqual(
            extract_merchant("Rs.500 paid to Amazon"),
            "Amazon",
        )

    def test_towards_merchant(self):
        self.assertEqual(
            extract_merchant("Rs.500 paid towards Flipkart"),
            "Flipkart",
        )

    def test_no_merchant(self):
        self.assertIsNone(
            extract_merchant("Rs.500 debited from your SBI account")
        )

    def test_merchant_with_stop_word(self):
        # "on" should stop merchant extraction
        self.assertEqual(
            extract_merchant("debited at Swiggy on 20-09-26"),
            "Swiggy",
        )

    def test_multi_word_merchant(self):
        self.assertEqual(
            extract_merchant("paid to Pizza Hut on 20-09-26"),
            "Pizza Hut",
        )


# ── Date Extraction ────────────────────────────────────────


class TestExtractTransactionDate(TestCase):

    def test_dd_mm_yy_dash(self):
        result = extract_transaction_date("debited on 20-09-26")
        self.assertEqual(result, datetime(2026, 9, 20))

    def test_dd_mm_yyyy_dash(self):
        result = extract_transaction_date("debited on 20-09-2026")
        self.assertEqual(result, datetime(2026, 9, 20))

    def test_dd_mm_yyyy_slash(self):
        result = extract_transaction_date("debited on 20/09/2026")
        self.assertEqual(result, datetime(2026, 9, 20))

    def test_ddmonyy(self):
        result = extract_transaction_date("debited 20SEP26")
        self.assertEqual(result, datetime(2026, 9, 20))

    def test_dd_mon_yyyy(self):
        result = extract_transaction_date("debited on 20-Sep-2026")
        self.assertEqual(result, datetime(2026, 9, 20))

    def test_datetime_with_time(self):
        result = extract_transaction_date("debited on 20-09-2026 14:30")
        self.assertEqual(result, datetime(2026, 9, 20, 14, 30))

    def test_no_date(self):
        self.assertIsNone(
            extract_transaction_date("Rs.500 debited from SBI")
        )


# ── Category Inference ─────────────────────────────────────


class TestInferCategory(TestCase):

    def test_food_swiggy(self):
        self.assertEqual(infer_category("Swiggy"), Category.FOOD)

    def test_food_zomato(self):
        self.assertEqual(infer_category("Zomato"), Category.FOOD)

    def test_shopping_amazon(self):
        self.assertEqual(infer_category("Amazon"), Category.SHOPPING)

    def test_shopping_flipkart(self):
        self.assertEqual(infer_category("Flipkart"), Category.SHOPPING)

    def test_travel_uber(self):
        self.assertEqual(infer_category("Uber"), Category.TRAVEL)

    def test_travel_ola(self):
        self.assertEqual(infer_category("Ola"), Category.TRAVEL)

    def test_unknown_merchant(self):
        self.assertEqual(infer_category("Some Shop"), Category.OTHER)

    def test_none_merchant(self):
        self.assertEqual(infer_category(None), Category.OTHER)


# ── Full Parser (parse_sms) ────────────────────────────────


class TestParseSms(TestCase):

    def test_basic_expense(self):
        result = parse_sms(
            "Rs.500 debited from your SBI account at Swiggy on 20-09-26"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["amount"], Decimal("500"))
        self.assertEqual(result["transaction_type"], TransactionType.EXPENSE)
        self.assertEqual(result["bank"], "SBI")
        self.assertEqual(result["merchant"], "Swiggy")
        self.assertEqual(result["category"], Category.FOOD)
        self.assertEqual(result["transaction_at"], datetime(2026, 9, 20))

    def test_basic_income(self):
        result = parse_sms(
            "INR 5,000.00 credited to your HDFC Bank account on 15-09-2026"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["amount"], Decimal("5000.00"))
        self.assertEqual(result["transaction_type"], TransactionType.INCOME)
        self.assertEqual(result["bank"], "HDFC")

    def test_expense_with_merchant(self):
        result = parse_sms(
            "₹1,200 spent at Amazon from ICICI Bank on 10/09/2026"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["amount"], Decimal("1200"))
        self.assertEqual(result["transaction_type"], TransactionType.EXPENSE)
        self.assertEqual(result["bank"], "ICICI")
        self.assertEqual(result["merchant"], "Amazon")
        self.assertEqual(result["category"], Category.SHOPPING)

    def test_no_merchant(self):
        result = parse_sms(
            "Rs.2000 debited from your Axis Bank account on 20-09-26"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["amount"], Decimal("2000"))
        self.assertEqual(result["bank"], "Axis")
        self.assertIsNone(result["merchant"])
        self.assertEqual(result["category"], Category.OTHER)

    def test_travel_category(self):
        result = parse_sms(
            "Rs.150 paid to Uber from SBI account"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["merchant"], "Uber")
        self.assertEqual(result["category"], Category.TRAVEL)

    def test_no_date(self):
        result = parse_sms(
            "Rs.500 debited from your SBI account at Swiggy"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["amount"], Decimal("500"))
        self.assertIsNone(result["transaction_at"])

    def test_non_transaction_sms(self):
        # No amount, no transaction keywords
        result = parse_sms("Your SBI branch will be closed tomorrow")
        self.assertIsNone(result)

    def test_no_amount(self):
        result = parse_sms("Amount debited from your SBI account")
        self.assertIsNone(result)

    def test_no_transaction_type(self):
        # Has amount and bank but no debit/credit keyword
        result = parse_sms("Your SBI account balance is Rs.5000")
        self.assertIsNone(result)

    def test_no_bank(self):
        result = parse_sms("Rs.500 debited from your account at Swiggy")
        self.assertIsNone(result)

    def test_empty_sms(self):
        self.assertIsNone(parse_sms(""))

    def test_none_sms(self):
        self.assertIsNone(parse_sms(None))

    def test_realistic_sbi_sms(self):
        result = parse_sms(
            "INR 2000 debited from A/c no. XX3423 on 05-02-26. "
            "SBI: purchase at Flipkart. Avl Bal- INR 2343.23."
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["amount"], Decimal("2000"))
        self.assertEqual(result["transaction_type"], TransactionType.EXPENSE)
        self.assertEqual(result["bank"], "SBI")
        self.assertEqual(result["merchant"], "Flipkart")
        self.assertEqual(result["category"], Category.SHOPPING)

    def test_realistic_hdfc_credit(self):
        result = parse_sms(
            "Your A/c XX6791 credited with INR 15,160.00 on 03-09-2026. "
            "HDFC Bank."
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["amount"], Decimal("15160.00"))
        self.assertEqual(result["transaction_type"], TransactionType.INCOME)
        self.assertEqual(result["bank"], "HDFC")

    def test_realistic_axis_sms(self):
        result = parse_sms(
            "Rs.350.00 spent at Zomato on Axis Bank Card XX4521 on 20SEP26"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["amount"], Decimal("350.00"))
        self.assertEqual(result["transaction_type"], TransactionType.EXPENSE)
        self.assertEqual(result["bank"], "Axis")
        self.assertEqual(result["merchant"], "Zomato")
        self.assertEqual(result["category"], Category.FOOD)
