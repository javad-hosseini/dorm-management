from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.core.exceptions import ImproperlyConfigured
import requests

from apps.sms_service.services.provider import (
    BaseSmsProvider,
    MeliPayamakRestProvider,
    ConsoleSmsProvider,
    get_sms_provider,
    ProviderResult,
)


class ProviderLayerTest(TestCase):
    def test_console_provider_succeeds(self):
        provider = ConsoleSmsProvider()
        res = provider.send_simple_sms(["09121112233"], "متن تست کنسول")
        self.assertTrue(res.success)
        self.assertTrue(res.rec_id.startswith("MOCK-"))

    def test_empty_recipients_or_text(self):
        prov = MeliPayamakRestProvider(
            api_token="test_token",
            from_number="50001234",
            base_url="http://mock.test",
        )
        res_empty_rec = prov.send_simple_sms([], "متن")
        self.assertFalse(res_empty_rec.success)
        self.assertEqual(res_empty_rec.error_code, "EMPTY_RECIPIENTS")

        res_empty_text = prov.send_simple_sms(["09121112233"], "   ")
        self.assertFalse(res_empty_text.success)
        self.assertEqual(res_empty_text.error_code, "EMPTY_TEXT")

    def test_melipayamak_missing_credentials_raises_exception(self):
        with self.assertRaises(ImproperlyConfigured):
            MeliPayamakRestProvider(api_token="", from_number="")

    @patch("requests.post")
    def test_melipayamak_successful_send(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"recId": 3741437414, "status": "ارسال اولیه با موفقیت انجام شد"}'
        mock_response.json.return_value = {
            "recId": 3741437414,
            "status": "ارسال اولیه با موفقیت انجام شد",
        }
        mock_post.return_value = mock_response

        prov = MeliPayamakRestProvider(
            api_token="e4a91aa15f634647892de8ea00eb5620",
            from_number="50004001985465",
            base_url="https://console.melipayamak.com/api/send/simple",
        )
        res = prov.send_simple_sms(["09121112233"], "تست وب‌سرویس جدید")

        self.assertTrue(res.success)
        self.assertEqual(res.rec_id, "3741437414")
        self.assertEqual(res.error_code, "ارسال اولیه با موفقیت انجام شد")

        # Verify request parameters
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(
            args[0],
            "https://console.melipayamak.com/api/send/simple/e4a91aa15f634647892de8ea00eb5620",
        )
        self.assertEqual(
            kwargs["json"],
            {
                "from": "50004001985465",
                "to": "09121112233",
                "text": "تست وب‌سرویس جدید",
            },
        )
        self.assertEqual(kwargs["headers"]["Content-Type"], "application/json")

    @patch("requests.post")
    def test_melipayamak_error_response_status_code(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"status": "2", "message": "اعتبار پنل کافی نیست"}'
        mock_response.json.return_value = {
            "status": "2",
            "message": "اعتبار پنل کافی نیست",
        }
        mock_post.return_value = mock_response

        prov = MeliPayamakRestProvider(
            api_token="token_abc",
            from_number="50001234",
            base_url="http://mock.test",
        )
        res = prov.send_simple_sms(["09121112233"], "تست اعتبار")

        self.assertFalse(res.success)
        self.assertEqual(res.error_code, "2")
        self.assertIn("اعتبار", res.error_message)

    @patch("requests.post")
    def test_melipayamak_http_401_unauthorized(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = '{"status": "توکن نامعتبر است"}'
        mock_response.json.return_value = {"status": "توکن نامعتبر است"}
        mock_post.return_value = mock_response

        prov = MeliPayamakRestProvider(
            api_token="bad_token",
            from_number="50001234",
            base_url="http://mock.test",
        )
        res = prov.send_simple_sms(["09121112233"], "تست")

        self.assertFalse(res.success)
        self.assertEqual(res.error_code, "HTTP_401")
        self.assertIn("توکن", res.error_message)

    @patch("requests.post")
    def test_melipayamak_http_500_invalid_json(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.json.side_effect = ValueError("No JSON")
        mock_post.return_value = mock_response

        prov = MeliPayamakRestProvider(
            api_token="token_xyz",
            from_number="50001234",
            base_url="http://mock.test",
        )
        res = prov.send_simple_sms(["09121112233"], "تست")

        self.assertFalse(res.success)
        self.assertEqual(res.error_code, "HTTP_500")

    @patch("requests.post")
    def test_melipayamak_timeout_handled_gracefully(self, mock_post):
        mock_post.side_effect = requests.exceptions.Timeout("Connection timed out")

        prov = MeliPayamakRestProvider(
            api_token="token_xyz",
            from_number="50001234",
            base_url="http://mock.test",
        )
        res = prov.send_simple_sms(["09121112233"], "تست")

        self.assertFalse(res.success)
        self.assertEqual(res.error_code, "TIMEOUT")
        self.assertIn("مهلت زمانی", res.error_message)

    @patch("requests.post")
    def test_melipayamak_connection_error_handled_gracefully(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectionError("Failed to connect")

        prov = MeliPayamakRestProvider(
            api_token="token_xyz",
            from_number="50001234",
            base_url="http://mock.test",
        )
        res = prov.send_simple_sms(["09121112233"], "تست")

        self.assertFalse(res.success)
        self.assertEqual(res.error_code, "CONNECTION_ERROR")
        self.assertIn("اتصال", res.error_message)

    @patch("requests.post")
    def test_melipayamak_token_sanitized_in_raw_response(self, mock_post):
        secret_token = "super_secret_token_12345"
        mock_response = MagicMock()
        mock_response.status_code = 400
        # Suppose the provider echoes back the token in raw response body
        mock_response.text = f'{{"error": "Invalid payload for token {secret_token}"}}'
        mock_response.json.return_value = {"error": f"Invalid payload for token {secret_token}"}
        mock_post.return_value = mock_response

        prov = MeliPayamakRestProvider(
            api_token=secret_token,
            from_number="50001234",
            base_url="http://mock.test",
        )
        res = prov.send_simple_sms(["09121112233"], "تست")

        self.assertNotIn(secret_token, res.raw_response)
        self.assertIn("***", res.raw_response)

    @patch("requests.post")
    def test_melipayamak_multiple_recipients_in_provider(self, mock_post):
        mock_response1 = MagicMock()
        mock_response1.status_code = 200
        mock_response1.text = '{"recId": 11111111, "status": "OK"}'
        mock_response1.json.return_value = {"recId": 11111111, "status": "OK"}

        mock_response2 = MagicMock()
        mock_response2.status_code = 200
        mock_response2.text = '{"recId": 22222222, "status": "OK"}'
        mock_response2.json.return_value = {"recId": 22222222, "status": "OK"}

        mock_post.side_effect = [mock_response1, mock_response2]

        prov = MeliPayamakRestProvider(
            api_token="token_abc",
            from_number="50001234",
            base_url="http://mock.test",
        )
        res = prov.send_simple_sms(["09121111111", "09122222222"], "تست چندگانه")

        self.assertTrue(res.success)
        self.assertEqual(res.rec_id, "11111111,22222222")
        self.assertEqual(mock_post.call_count, 2)

    @override_settings(SMS_CONSOLE_MODE=True)
    def test_get_sms_provider_returns_console_mode(self):
        prov = get_sms_provider()
        self.assertIsInstance(prov, ConsoleSmsProvider)

    @override_settings(
        SMS_CONSOLE_MODE=False,
        MELIPAYAMAK_API_TOKEN="valid_token",
        MELIPAYAMAK_SENDER="50001234",
    )
    def test_get_sms_provider_returns_rest_provider_when_configured(self):
        prov = get_sms_provider()
        self.assertIsInstance(prov, MeliPayamakRestProvider)
        self.assertEqual(prov.api_token, "valid_token")
        self.assertEqual(prov.from_number, "50001234")

    @patch("requests.post")
    def test_blacklist_detection_via_code_and_text(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"recId": 22, "status": "شماره در لیست سیاه است"}'
        mock_response.json.return_value = {
            "recId": 22,
            "status": "شماره در لیست سیاه است",
        }
        mock_post.return_value = mock_response

        prov = MeliPayamakRestProvider(
            api_token="token_abc",
            from_number="50001234",
            base_url="http://mock.test",
        )
        res = prov.send_simple_sms(["09121112233"], "تست بلک لیست")

        self.assertFalse(res.success)
        self.assertTrue(res.is_blacklist)
        self.assertEqual(res.error_code, "BLACKLIST")
        self.assertIn("لیست سیاه", res.error_message)
