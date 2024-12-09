import time
from datetime import datetime
from email.utils import COMMASPACE

from odoo import fields, models


class MailMail(models.Model):
    _inherit = "mail.mail"

    def _tracking_email_value(self, email):
        """Return email.activity.tracking record values"""
        ts = time.time()
        dt = datetime.utcfromtimestamp(ts)
        email_to_list = email.get("email_to", [])
        email_to = COMMASPACE.join(email_to_list)
        return {
            "name": self.subject,
            "timestamp": "%.6f" % ts,
            "time": fields.Datetime.to_string(dt),
            "mail_id": self.id,
            "mail_message_id": self.mail_message_id.id,
            "partner_id": (email.get("partner_id") or self.env["res.partner"]).id,
            "recipient": email_to,
            "sender": self.email_from,
        }

    def _prepare_outgoing_list(self, recipients_follower_status=None):
        """
            Creates a `mail.activity.tracking` record and appends the tracking image to the email. 
            Please note that, due to the inability to add mail headers in this function, 
            the tracking image added here will later be utilized in the `IrMailServer.build_email` 
            method to extract the `mail.activity.tracking` record ID and set the `X-Odoo-MailTracking-ID` header.
        """
        emails = super()._prepare_outgoing_list(recipients_follower_status)
        for email in emails:
            vals = self._tracking_email_value(email)
            tracking_email = self.env["mail.activity.tracking"].sudo().with_context(res_model=self.model, record_id=self.res_id).create(vals)
            tracking_email.tracking_img_add(email)
        return emails
