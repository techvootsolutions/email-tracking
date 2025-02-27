from contextlib import contextmanager, suppress
from unittest.mock import patch

from freezegun import freeze_time
from werkzeug.exceptions import NotAcceptable

from odoo.exceptions import MissingError, UserError, ValidationError
from odoo.tests.common import Form, TransactionCase
from odoo.tools import mute_logger

from ..controllers.main import MailTrackingController

# HACK https://github.com/odoo/odoo/pull/78424 because website is not dependency
try:
    from odoo.addons.website.tools import MockRequest
except ImportError:
    MockRequest = None


_packagepath = "odoo.addons.mail_activity_tracking"


@freeze_time("2016-08-12 17:00:00", tick=True)
class TestMailgun(TransactionCase):
    def mail_send(self):
        mail = self.env["mail.mail"].create(
            {
                "subject": "Test subject",
                "email_from": "from@example.com",
                "email_to": self.recipient,
                "body_html": "<p>This is a test message</p>",
                "message_id": "<test-id@f187c54734e8>",
            }
        )
        mail.send()
        # Search tracking created
        tracking_email = self.env["mail.activity.tracking"].search(
            [("mail_id", "=", mail.id)]
        )
        return mail, tracking_email

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.recipient = "to@example.com"
        cls.mail, cls.tracking_email = cls.mail_send(cls)
        cls.domain = "example.com"
        # Configure Mailgun through GUI
        cf = Form(cls.env["res.config.settings"])
        cf.mail_tracking_mailgun_enabled = True
        cf.mail_tracking_mailgun_api_key = (
            cf.mail_tracking_mailgun_webhook_signing_key
        ) = (
            cf.mail_tracking_mailgun_validation_key
        ) = "key-12345678901234567890123456789012"
        cf.mail_tracking_mailgun_domain = False
        config = cf.save()
        # Done this way as `hr_expense` adds this field again as readonly, and thus Form
        # doesn't process it correctly
        # Catchall + Alias
        cls.alias_domain = cls.env["mail.alias.domain"].create(
            {"catchall_alias": "TheCatchall", "name": cls.domain}
        )
        config.execute()
        cls.token = "f1349299097a51b9a7d886fcb5c2735b426ba200ada6e9e149"
        cls.timestamp = "1471021089"
        cls.signature = (
            "4fb6d4dbbe10ce5d620265dcd7a3c0b8" "ca0dede1433103891bc1ae4086e9d5b2"
        )
        cls.event = {
            "log-level": "info",
            "id": "oXAVv5URCF-dKv8c6Sa7T",
            "timestamp": 1471021089.0,
            "message": {
                "headers": {
                    "to": "test@test.com",
                    "message-id": "test-id@f187c54734e8",
                    "from": "Mr. Odoo <mrodoo@odoo.com>",
                    "subject": "This is a test",
                },
            },
            "event": "delivered",
            "recipient": "to@example.com",
            "user-variables": {
                "odoo_db": cls.env.cr.dbname,
                "tracking_email_id": cls.tracking_email.id,
            },
        }
        cls.metadata = {
            "ip": "127.0.0.1",
            "user_agent": False,
            "os_family": False,
            "ua_family": False,
        }
        cls.partner = cls.env["res.partner"].create(
            {"name": "Mr. Odoo", "email": "mrodoo@example.com"}
        )
        cls.response = {"items": [cls.event]}
        cls.MailTrackingController = MailTrackingController()

    @contextmanager
    def _request_mock(self, reset_replay_cache=True):
        # HACK https://github.com/odoo/odoo/pull/78424
        if MockRequest is None:
            self.skipTest("MockRequest not found, sorry")
        if reset_replay_cache:
            with suppress(AttributeError):
                del self.env.registry._mail_tracking_mailgun_processed_tokens
        # Imitate Mailgun JSON request
        mock = MockRequest(self.env)
        with mock as request:
            request.dispatcher.jsonrequest = {
                "signature": {
                    "timestamp": self.timestamp,
                    "token": self.token,
                    "signature": self.signature,
                },
                "event-data": self.event,
            }
            request.params = {"db": self.env.cr.dbname}
            request.session.db = self.env.cr.dbname
            yield request

    def event_search(self, event_type):
        event = self.env["mail.activity.event"].search(
            [
                ("tracking_email_id", "=", self.tracking_email.id),
                ("event_type", "=", event_type),
            ]
        )
        self.assertTrue(event)
        return event

    def test_no_api_key(self):
        self.env["ir.config_parameter"].set_param("mailgun.apikey", "")
        with self.assertRaises(ValidationError):
            self.env["mail.activity.tracking"]._mailgun_values()

    def test_no_domain(self):
        # Avoid pre-existing domains
        self.env["mail.alias"].search(
            [("alias_domain_id", "!=", False)]
        ).alias_domain_id = False
        self.env["mail.alias.domain"].search([]).unlink()
        with self.assertRaises(ValidationError):
            self.env["mail.activity.tracking"]._mailgun_values()
        # Now we set an specific domain for Mailgun:
        # i.e: we configure new EU zone without loosing old domain statistics
        self.env["ir.config_parameter"].set_param("mailgun.domain", "eu.example.com")
        self.test_event_delivered()

    @mute_logger("odoo.addons.mail_activity_tracking.models.mail_activity_tracking")
    def test_bad_signature(self):
        self.signature = "bad_signature"
        with self._request_mock(), self.assertRaises(NotAcceptable):
            self.MailTrackingController.mail_tracking_mailgun_webhook()

    @mute_logger("odoo.addons.mail_activity_tracking.models.mail_activity_tracking")
    def test_bad_event_type(self):
        old_events = self.tracking_email.tracking_event_ids
        self.event.update({"event": "bad_event"})
        with self._request_mock():
            self.MailTrackingController.mail_tracking_mailgun_webhook()
        self.assertFalse(self.tracking_email.tracking_event_ids - old_events)

    def test_bad_ts(self):
        self.timestamp = "7a"  # Now time will be used instead
        self.signature = (
            "06cc05680f6e8110e59b41152b2d1c0f1045d755ef2880ff922344325c89a6d4"
        )
        with self._request_mock(), self.assertRaises(ValueError):
            self.MailTrackingController.mail_tracking_mailgun_webhook()

    @mute_logger("odoo.addons.mail_activity_tracking.models.mail_activity_tracking")
    def test_tracking_not_found(self):
        self.event.update(
            {
                "event": "delivered",
                "message": {
                    "headers": {
                        "to": "else@test.com",
                        "message-id": "test-id-else@f187c54734e8",
                        "from": "Mr. Odoo <mrodoo@odoo.com>",
                        "subject": "This is a bad test",
                    },
                },
                "user-variables": {
                    "odoo_db": self.env.cr.dbname,
                    "tracking_email_id": -1,
                },
            }
        )
        with self._request_mock(), self.assertRaises(MissingError):
            self.MailTrackingController.mail_tracking_mailgun_webhook()

    def test_tracking_wrong_db(self):
        self.event["user-variables"]["odoo_db"] = "%s_nope" % self.env.cr.dbname
        with self._request_mock(), self.assertLogs(level="ERROR") as log_catcher:
            self.MailTrackingController.mail_tracking_mailgun_webhook()
        self.assertIn(
            f"Mailgun: event for DB {self.env.cr.dbname}_nope "
            f"received in DB {self.env.cr.dbname}",
            log_catcher.output[0],
        )

    def test_tracking_not_odoo_event(self):
        self.event["user-variables"].pop("odoo_db")
        with self._request_mock(), self.assertLogs(level="DEBUG") as log_catcher:
            self.MailTrackingController.mail_tracking_mailgun_webhook()
        self.assertIn("Mailgun: dropping not Odoo event", log_catcher.output[-1:][0])

    # https://documentation.mailgun.com/en/latest/user_manual.html#tracking-deliveries
    def test_event_delivered(self):
        self.event.update({"event": "delivered"})
        with self._request_mock():
            self.MailTrackingController.mail_tracking_mailgun_webhook()
        events = self.event_search("delivered")
        for event in events:
            self.assertEqual(event.timestamp, float(self.timestamp))
            self.assertEqual(event.recipient, self.recipient)

    # https://documentation.mailgun.com/en/latest/user_manual.html#tracking-opens
    def test_event_opened(self):
        ip = "127.0.0.1"
        user_agent = "Odoo Test/8.0 Gecko Firefox/11.0"
        os_family = "Linux"
        ua_family = "Firefox"
        ua_type = "browser"
        self.event.update(
            {
                "event": "opened",
                "city": "Mountain View",
                "country": "US",
                "region": "CA",
                "client-name": ua_family,
                "client-os": os_family,
                "client-type": ua_type,
                "device-type": "desktop",
                "ip": ip,
                "user-agent": user_agent,
            }
        )
        with self._request_mock():
            self.MailTrackingController.mail_tracking_mailgun_webhook()
        event = self.event_search("open")
        self.assertEqual(event.timestamp, float(self.timestamp))
        self.assertEqual(event.recipient, self.recipient)
        self.assertEqual(event.ip, ip)
        self.assertEqual(event.user_agent, user_agent)
        self.assertEqual(event.os_family, os_family)
        self.assertEqual(event.ua_family, ua_family)
        self.assertEqual(event.ua_type, ua_type)
        self.assertEqual(event.mobile, False)
        self.assertEqual(event.user_country_id.code, "US")

    # https://documentation.mailgun.com/en/latest/user_manual.html#tracking-clicks
    def test_event_clicked(self):
        ip = "127.0.0.1"
        user_agent = "Odoo Test/8.0 Gecko Firefox/11.0"
        os_family = "Linux"
        ua_family = "Firefox"
        ua_type = "browser"
        url = "https://www.techvoot.com"
        self.event.update(
            {
                "event": "clicked",
                "city": "Mountain View",
                "country": "US",
                "region": "CA",
                "client-name": ua_family,
                "client-os": os_family,
                "client-type": ua_type,
                "device-type": "tablet",
                "ip": ip,
                "user-agent": user_agent,
                "url": url,
            }
        )
        with self._request_mock():
            self.MailTrackingController.mail_tracking_mailgun_webhook()
        event = self.event_search("click")
        self.assertEqual(event.timestamp, float(self.timestamp))
        self.assertEqual(event.recipient, self.recipient)
        self.assertEqual(event.ip, ip)
        self.assertEqual(event.user_agent, user_agent)
        self.assertEqual(event.os_family, os_family)
        self.assertEqual(event.ua_family, ua_family)
        self.assertEqual(event.ua_type, ua_type)
        self.assertEqual(event.mobile, True)
        self.assertEqual(event.url, url)

    # https://documentation.mailgun.com/en/latest/user_manual.html#tracking-unsubscribes
    def test_event_unsubscribed(self):
        ip = "127.0.0.1"
        user_agent = "Odoo Test/8.0 Gecko Firefox/11.0"
        os_family = "Linux"
        ua_family = "Firefox"
        ua_type = "browser"
        self.event.update(
            {
                "event": "unsub",
                "city": "Mountain View",
                "country": "US",
                "region": "CA",
                "client-name": ua_family,
                "client-os": os_family,
                "client-type": ua_type,
                "device-type": "mobile",
                "ip": ip,
                "user-agent": user_agent,
            }
        )
        with self._request_mock():
            self.MailTrackingController.mail_tracking_mailgun_webhook()
        event = self.event_search("unsub")
        self.assertEqual(event.timestamp, float(self.timestamp))
        self.assertEqual(event.recipient, self.recipient)
        self.assertEqual(event.ip, ip)
        self.assertEqual(event.user_agent, user_agent)
        self.assertEqual(event.os_family, os_family)
        self.assertEqual(event.ua_family, ua_family)
        self.assertEqual(event.ua_type, ua_type)
        self.assertEqual(event.mobile, True)

    # https://documentation.mailgun.com/en/latest/user_manual.html#tracking-spam-complaints
    def test_event_complained(self):
        self.event.update({"event": "complained"})
        with self._request_mock():
            self.MailTrackingController.mail_tracking_mailgun_webhook()
        event = self.event_search("spam")
        self.assertEqual(event.timestamp, float(self.timestamp))
        self.assertEqual(event.recipient, self.recipient)
        self.assertEqual(event.error_type, "spam")

    # https://documentation.mailgun.com/en/latest/user_manual.html#tracking-bounces
    def test_event_failed(self):
        code = 550
        error = (
            "5.1.1 The email account does not exist.\n"
            "5.1.1 double-checking the recipient's email address"
        )
        notification = "Please, check recipient's email address"
        self.event.update(
            {
                "event": "failed",
                "delivery-status": {
                    "attempt-no": 1,
                    "code": code,
                    "description": notification,
                    "message": error,
                    "session-seconds": 0.0,
                },
                "severity": "permanent",
            }
        )
        with self._request_mock():
            self.MailTrackingController.mail_tracking_mailgun_webhook()
        event = self.event_search("hard_bounce")
        self.assertEqual(event.timestamp, float(self.timestamp))
        self.assertEqual(event.recipient, self.recipient)
        self.assertEqual(event.error_type, str(code))
        self.assertEqual(event.error_description, error)
        self.assertEqual(event.error_details, notification)

    def test_event_rejected(self):
        reason = "hardfail"
        description = "Not delivering to previously bounced address"
        self.event.update(
            {
                "event": "rejected",
                "reject": {"reason": reason, "description": description},
            }
        )
        with self._request_mock():
            self.MailTrackingController.mail_tracking_mailgun_webhook()
        event = self.event_search("reject")
        self.assertEqual(event.timestamp, float(self.timestamp))
        self.assertEqual(event.recipient, self.recipient)
        self.assertEqual(event.error_type, "rejected")
        self.assertEqual(event.error_description, reason)
        self.assertEqual(event.error_details, description)

    @patch(f"{_packagepath}.models.res_partner.requests")
    def test_email_validity(self, mock_request):
        self.partner.email_bounced = False
        mock_request.get.return_value.apparent_encoding = "ascii"
        mock_request.get.return_value.status_code = 200
        mock_request.get.return_value.json.return_value = {
            "is_valid": True,
            "mailbox_verification": "true",
        }
        self.partner.email = "info@techvoot.com"
        self.assertFalse(self.partner.email_bounced)
        self.partner.email = "xoxoxoxo@techvoot.com"
        # Not a valid mailbox
        mock_request.get.return_value.json.return_value = {
            "is_valid": True,
            "mailbox_verification": "false",
        }
        with self.assertRaises(UserError):
            self.partner.check_email_validity()
        # Not a valid mail address
        mock_request.get.return_value.json.return_value = {
            "is_valid": False,
            "mailbox_verification": "false",
        }
        with self.assertRaises(UserError):
            self.partner.check_email_validity()
        # If we autocheck, the mail will be bounced
        self.partner.with_context(mailgun_auto_check=True).check_email_validity()
        self.assertTrue(self.partner.email_bounced)
        # Unable to fully validate
        mock_request.get.return_value.json.return_value = {
            "is_valid": True,
            "mailbox_verification": "unknown",
        }
        with self.assertRaises(UserError):
            self.partner.check_email_validity()

    @patch(f"{_packagepath}.models.res_partner.requests")
    def test_email_validity_exceptions(self, mock_request):
        mock_request.get.return_value.status_code = 404
        with self.assertRaises(UserError):
            self.partner.check_email_validity()
        self.env["ir.config_parameter"].set_param("mailgun.validation_key", "")
        with self.assertRaises(UserError):
            self.partner.check_email_validity()

    @patch(f"{_packagepath}.models.res_partner.requests")
    def test_bounced(self, mock_request):
        self.partner.email_bounced = True
        mock_request.get.return_value.status_code = 404
        self.partner.check_email_bounced()
        self.assertFalse(self.partner.email_bounced)
        mock_request.get.return_value.status_code = 200
        self.partner.force_set_bounced()
        self.partner.check_email_bounced()
        self.assertTrue(self.partner.email_bounced)
        mock_request.delete.return_value.status_code = 200
        self.partner.force_unset_bounced()
        self.assertFalse(self.partner.email_bounced)

    def test_email_bounced_set(self):
        message_number = len(self.partner.message_ids) + 1
        self.partner._email_bounced_set("test_error", False)
        self.assertEqual(len(self.partner.message_ids), message_number)
        self.partner.email = ""
        self.partner._email_bounced_set("test_error", False)
        self.assertEqual(len(self.partner.message_ids), message_number)

    @patch(f"{_packagepath}.models.mail_activity_tracking.requests")
    def test_manual_check(self, mock_request):
        mock_request.get.return_value.json.return_value = self.response
        mock_request.get.return_value.status_code = 200
        self.tracking_email.action_manual_check_mailgun()
        event = self.env["mail.activity.event"].search(
            [("mailgun_id", "=", self.response["items"][0]["id"])]
        )
        self.assertTrue(event)
        self.assertEqual(event.event_type, self.response["items"][0]["event"])

    @patch(f"{_packagepath}.models.mail_activity_tracking.requests")
    def test_manual_check_exceptions(self, mock_request):
        mock_request.get.return_value.status_code = 404
        with self.assertRaises(UserError):
            self.tracking_email.action_manual_check_mailgun()
        mock_request.get.return_value.status_code = 200
        mock_request.get.return_value.json.return_value = {}
        with self.assertRaises(UserError):
            self.tracking_email.action_manual_check_mailgun()
