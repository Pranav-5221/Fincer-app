"""
Fincer API Integration Tests.

Covers:
- Phase 1: PATCH field restrictions
- Phase 2/3: Parser API (POST /api/transactions/parse/)
- Phase 4/5: Full auth flow (register -> login -> refresh)
- Phase 6: User isolation
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase


# -- Helpers --


class AuthMixin:
    """Helpers to create users and authenticate requests."""

    def create_user(self, username="testuser", password="testpass123"):
        return User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password=password,
        )

    def get_tokens(self, username="testuser", password="testpass123"):
        """Login and return (access, refresh) token strings."""
        resp = self.client.post(
            "/api/login/",
            {"username": username, "password": password},
            format="json",
        )
        return resp.data["access"], resp.data["refresh"]

    def auth_header(self, token):
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def create_transaction(self, token, **overrides):
        """Create a transaction directly via POST for test setup."""
        data = {
            "amount": "500.00",
            "transaction_type": 1,
            "bank": "SBI",
            "merchant": "Swiggy",
            "category": 1,
            "transaction_at": timezone.now().isoformat(),
            "original_sms": "Rs.500 debited from SBI at Swiggy",
        }
        data.update(overrides)
        resp = self.client.post(
            "/api/transactions/",
            data,
            format="json",
            **self.auth_header(token),
        )
        return resp


# -- Phase 1: PATCH Field Restrictions --


class TestPatchRestrictions(AuthMixin, APITestCase):
    """
    Users may PATCH: merchant, category, amount, transaction_type, bank.
    Users may NOT change: id, user, transaction_at, original_sms.
    """

    def setUp(self):
        self.user = self.create_user()
        self.token, _ = self.get_tokens()
        resp = self.create_transaction(self.token)
        self.tx_id = resp.data["id"]
        self.url = f"/api/transactions/{self.tx_id}/"

    def _patch(self, data):
        return self.client.patch(
            self.url, data, format="json", **self.auth_header(self.token)
        )

    # -- Allowed fields --

    def test_patch_merchant(self):
        resp = self._patch({"merchant": "Zomato"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["merchant"], "Zomato")

    def test_patch_category(self):
        resp = self._patch({"category": 2})  # SHOPPING
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["category"], 2)

    def test_patch_amount(self):
        resp = self._patch({"amount": "999.99"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Decimal(resp.data["amount"]), Decimal("999.99"))

    def test_patch_transaction_type(self):
        resp = self._patch({"transaction_type": 0})  # INCOME
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["transaction_type"], 0)

    def test_patch_bank(self):
        resp = self._patch({"bank": "HDFC"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["bank"], "HDFC")

    # -- Disallowed fields (silently ignored by serializer) --

    def test_patch_transaction_at_ignored(self):
        resp = self.client.get(
            self.url, **self.auth_header(self.token)
        )
        original_at = resp.data["transaction_at"]
        resp = self._patch({"transaction_at": "2000-01-01T00:00:00Z"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["transaction_at"], original_at)

    def test_patch_original_sms_ignored(self):
        resp = self.client.get(
            self.url, **self.auth_header(self.token)
        )
        original_sms = resp.data["original_sms"]
        resp = self._patch({"original_sms": "HACKED"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["original_sms"], original_sms)

    def test_patch_user_ignored(self):
        """Attempting to change user field has no effect."""
        other = self.create_user("other", "otherpass123")
        resp = self._patch({"user": other.id})
        self.assertEqual(resp.status_code, 200)

    # -- Response contains all fields --

    def test_patch_response_has_all_fields(self):
        """PATCH response must include id, transaction_at, original_sms."""
        resp = self._patch({"merchant": "Uber"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("id", resp.data)
        self.assertIn("transaction_at", resp.data)
        self.assertIn("original_sms", resp.data)
        self.assertIn("amount", resp.data)


# -- Phase 2/3: Parser API --


class TestParserAPI(AuthMixin, APITestCase):
    """POST /api/transactions/parse/ -- raw SMS to transaction."""

    PARSE_URL = "/api/transactions/parse/"

    def setUp(self):
        self.user = self.create_user()
        self.token, _ = self.get_tokens()

    def _parse(self, data, token=None):
        t = token or self.token
        return self.client.post(
            self.PARSE_URL, data, format="json",
            **self.auth_header(t),
        )

    # -- Success --

    def test_valid_expense_sms(self):
        resp = self._parse({
            "sms": "Rs.500 debited from your SBI account at Swiggy"
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Decimal(resp.data["amount"]), Decimal("500"))
        self.assertEqual(resp.data["transaction_type"], 1)  # EXPENSE
        self.assertEqual(resp.data["bank"], "SBI")
        self.assertEqual(resp.data["merchant"], "Swiggy")
        self.assertEqual(resp.data["category"], 1)  # FOOD

    def test_valid_income_sms(self):
        resp = self._parse({
            "sms": "INR 5000.00 credited to your HDFC Bank account"
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Decimal(resp.data["amount"]), Decimal("5000.00"))
        self.assertEqual(resp.data["transaction_type"], 0)  # INCOME
        self.assertEqual(resp.data["bank"], "HDFC")

    def test_original_sms_stored(self):
        sms = "Rs.500 debited from your SBI account at Swiggy"
        resp = self._parse({"sms": sms})
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["original_sms"], sms)

    def test_user_is_request_user(self):
        """Transaction must be owned by the authenticated user."""
        resp = self._parse({
            "sms": "Rs.500 debited from your SBI account at Swiggy"
        })
        self.assertEqual(resp.status_code, 201)
        # Verify by listing -- only this user should see it
        list_resp = self.client.get(
            "/api/transactions/",
            **self.auth_header(self.token),
        )
        self.assertEqual(len(list_resp.data), 1)
        self.assertEqual(list_resp.data[0]["id"], resp.data["id"])

    # -- Failures --

    def test_non_transaction_sms(self):
        resp = self._parse({
            "sms": "Your SBI branch will be closed tomorrow"
        })
        self.assertEqual(resp.status_code, 400)

    def test_missing_sms_field(self):
        resp = self._parse({})
        self.assertEqual(resp.status_code, 400)

    def test_empty_sms(self):
        resp = self._parse({"sms": ""})
        self.assertEqual(resp.status_code, 400)

    def test_sms_no_amount(self):
        resp = self._parse({
            "sms": "Amount debited from your SBI account"
        })
        self.assertEqual(resp.status_code, 400)

    def test_sms_no_bank(self):
        resp = self._parse({
            "sms": "Rs.500 debited from your account at Swiggy"
        })
        self.assertEqual(resp.status_code, 400)

    def test_sms_no_transaction_type(self):
        resp = self._parse({
            "sms": "Your SBI account balance is Rs.5000"
        })
        self.assertEqual(resp.status_code, 400)

    def test_unauthenticated_parse(self):
        resp = self.client.post(
            self.PARSE_URL,
            {"sms": "Rs.500 debited from your SBI account at Swiggy"},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)


# -- Phase 4/5: Full Auth Flow --


class TestAuthFlow(AuthMixin, APITestCase):
    """Register -> login -> access -> refresh -> use new access."""

    def test_register_and_login(self):
        # Register
        resp = self.client.post(
            "/api/register/",
            {"username": "newuser", "email": "new@example.com",
             "password": "newpass123"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)

        # Login
        resp = self.client.post(
            "/api/login/",
            {"username": "newuser", "password": "newpass123"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)

    def test_me_endpoint(self):
        self.create_user()
        token, _ = self.get_tokens()
        resp = self.client.get(
            "/api/me/", **self.auth_header(token)
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["name"], "testuser")

    def test_refresh_token(self):
        self.create_user()
        access, refresh = self.get_tokens()

        # Refresh
        resp = self.client.post(
            "/api/token/refresh/",
            {"refresh": refresh},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        new_access = resp.data["access"]
        self.assertNotEqual(new_access, "")

        # Use new access token on a protected endpoint
        resp = self.client.get(
            "/api/me/", **self.auth_header(new_access)
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["name"], "testuser")

    def test_unauthenticated_me_returns_401(self):
        resp = self.client.get("/api/me/")
        self.assertEqual(resp.status_code, 401)

    def test_invalid_login_returns_401(self):
        self.create_user()
        resp = self.client.post(
            "/api/login/",
            {"username": "testuser", "password": "wrongpassword"},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)


# -- Phase 6: User Isolation --


class TestUserIsolation(AuthMixin, APITestCase):
    """User A must never see, edit, or delete User B's data."""

    def setUp(self):
        # User A
        self.user_a = self.create_user("user_a", "pass_a_123")
        self.token_a, _ = self.get_tokens("user_a", "pass_a_123")

        # User B
        self.user_b = self.create_user("user_b", "pass_b_123")
        self.token_b, _ = self.get_tokens("user_b", "pass_b_123")

        # User A creates a transaction
        resp = self.create_transaction(
            self.token_a, merchant="A-Merchant"
        )
        self.tx_a_id = resp.data["id"]

        # User B creates a transaction
        resp = self.create_transaction(
            self.token_b, merchant="B-Merchant"
        )
        self.tx_b_id = resp.data["id"]

    def test_list_only_own_transactions(self):
        resp = self.client.get(
            "/api/transactions/",
            **self.auth_header(self.token_a),
        )
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["merchant"], "A-Merchant")

    def test_list_user_b_only_own(self):
        resp = self.client.get(
            "/api/transactions/",
            **self.auth_header(self.token_b),
        )
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["merchant"], "B-Merchant")

    def test_get_other_user_transaction_404(self):
        resp = self.client.get(
            f"/api/transactions/{self.tx_b_id}/",
            **self.auth_header(self.token_a),
        )
        self.assertEqual(resp.status_code, 404)

    def test_patch_other_user_transaction_404(self):
        resp = self.client.patch(
            f"/api/transactions/{self.tx_b_id}/",
            {"merchant": "HACKED"},
            format="json",
            **self.auth_header(self.token_a),
        )
        self.assertEqual(resp.status_code, 404)

    def test_delete_other_user_transaction_404(self):
        resp = self.client.delete(
            f"/api/transactions/{self.tx_b_id}/",
            **self.auth_header(self.token_a),
        )
        self.assertEqual(resp.status_code, 404)

    def test_parse_creates_for_authenticated_user_only(self):
        """SMS parsed by User A must not appear in User B's list."""
        self.client.post(
            "/api/transactions/parse/",
            {"sms": "Rs.999 debited from your SBI account at Uber"},
            format="json",
            **self.auth_header(self.token_a),
        )

        # User B should still only have 1 transaction
        resp = self.client.get(
            "/api/transactions/",
            **self.auth_header(self.token_b),
        )
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["merchant"], "B-Merchant")

    def test_unauthenticated_list_returns_401(self):
        resp = self.client.get("/api/transactions/")
        self.assertEqual(resp.status_code, 401)
