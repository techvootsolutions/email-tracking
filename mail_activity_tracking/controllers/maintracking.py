import hashlib
import hmac
import logging
import base64
from datetime import datetime, timedelta
from contextlib import contextmanager
from werkzeug.exceptions import NotAcceptable
from odoo.exceptions import ValidationError
from odoo.http import request, route
from odoo.addons.web.controllers.utils import ensure_db

import werkzeug

import odoo
from odoo import SUPERUSER_ID, api, http, _

from odoo.addons.mail.controllers.mail import MailController

_logger = logging.getLogger(__name__)

BLANK = "R0lGODlhAQABAIAAANvf7wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw=="


@contextmanager
def db_env(dbname):
    if not http.db_filter([dbname]):
        raise werkzeug.exceptions.BadRequest()
    cr = None
    if dbname == http.request.db:
        cr = http.request.cr
    if not cr:
        cr = odoo.sql_db.db_connect(dbname).cursor()
    yield api.Environment(cr, SUPERUSER_ID, {})


class MailTrackingController(MailController):
    def _request_metadata(self):
        """Prepare remote info metadata"""
        request = http.request.httprequest
        return {
            "ip": request.remote_addr or False,
            "user_agent": request.user_agent or False,
            "os_family": request.user_agent.platform or False,
            "ua_family": request.user_agent.browser or False,
        }

    @http.route(
        [
            "/mail/tracking/open/<string:db>/<int:tracking_email_id>/blank.gif",
            "/mail/tracking/open/<string:db>"
            "/<int:tracking_email_id>/<string:token>/blank.gif",
        ],
        type="http",
        auth="none",
        methods=["GET"],
    )
    def mail_tracking_open(self, db, tracking_email_id, token=False, **kw):
        """Route used to track mail openned (With & Without Token)"""
        metadata = self._request_metadata()
        with db_env(db) as env:
            try:
                tracking_email = (
                    env["mail.activity.tracking"]
                    .sudo()
                    .search([("id", "=", tracking_email_id), ("token", "=", token)])
                )
                if not tracking_email:
                    _logger.warning(
                        "MailTracking email '%s' not found", tracking_email_id
                    )
                elif tracking_email.state in ("sent", "delivered"):
                    tracking_email.event_create("open", metadata)
            except Exception as e:
                _logger.warning(e)

        # Always return GIF blank image
        response = werkzeug.wrappers.Response()
        response.mimetype = "image/gif"
        response.data = base64.b64decode(BLANK)
        return response

    def _mail_tracking_mailgun_webhook_verify(self, timestamp, token, signature):
        """Protect against potential Mailgun webhook attacks.

                For more details, refer to the Mailgun documentation on securing webhooks:
                https://documentation.mailgun.com/en/latest/user_manual.html#securing-webhooks
        """  # noqa: E501
        # Request cannot be old
        processing_time = datetime.utcnow() - datetime.utcfromtimestamp(int(timestamp))
        if not timedelta() < processing_time < timedelta(minutes=10):
            raise ValidationError(_("Request is too old"))
        # Avoid replay attacks
        try:
            processed_tokens = (
                request.env.registry._mail_tracking_mailgun_processed_tokens
            )
        except AttributeError:
            processed_tokens = (
                request.env.registry._mail_tracking_mailgun_processed_tokens
            ) = set()
        if token in processed_tokens:
            raise ValidationError(_("Request was already processed"))
        processed_tokens.add(token)
        params = request.env["mail.activity.tracking"]._mailgun_values()
        # Assert signature
        if not params.webhook_signing_key:
            _logger.warning(
                "Skipping webhook payload verification. "
                "Set `mailgun.webhook_signing_key` config parameter to enable"
            )
            return
        hmac_digest = hmac.new(
            key=params.webhook_signing_key.encode(),
            msg=(f"{timestamp}{token}").encode(),
            digestmod=hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(str(signature), str(hmac_digest)):
            raise ValidationError(_("Wrong signature"))

    @route(["/mail/tracking/mailgun/all"], auth="none", type="json", csrf=False)
    def mail_tracking_mailgun_webhook(self):
        """Handles and processes incoming webhook events from Mailgun."""
        ensure_db()
        # Verify and return 406 in case of failure, to avoid retries
        # See https://documentation.mailgun.com/en/latest/user_manual.html#routes
        try:
            self._mail_tracking_mailgun_webhook_verify(
                **request.dispatcher.jsonrequest["signature"]
            )
        except ValidationError as error:
            raise NotAcceptable from error
        # Process event
        request.env["mail.activity.tracking"].sudo()._mailgun_event_process(
            request.dispatcher.jsonrequest["event-data"],
            self._request_metadata(),
        )
