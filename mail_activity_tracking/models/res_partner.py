from urllib.parse import urljoin

import requests

from odoo import api, fields, models, SUPERUSER_ID, _
from odoo.exceptions import UserError

from ..wizards.res_config_settings import MAILGUN_TIMEOUT


class ResPartner(models.Model):
    _name = "res.partner"
    _inherit = ["res.partner", "mail.bounced.mixin"]

    # tracking_emails_count and email_score are non-store fields in order
    # to improve performance
    tracking_emails_count = fields.Integer(
        compute="_compute_email_score_and_count", readonly=True
    )
    email_score = fields.Float(compute="_compute_email_score_and_count", readonly=True)

    @api.depends("email")
    def _compute_email_score_and_count(self):
        self.email_score = 50.0
        self.tracking_emails_count = 0
        partners_mail = self.filtered("email")
        mt_obj = self.env["mail.activity.tracking"].sudo()
        for partner in partners_mail:
            partner.email_score = mt_obj.email_score_from_email(partner.email)
            # We don't want performance issues due to heavy ACLs check for large
            # recordsets. Our option is to hide the number for regular users.
            if not self.env.user.has_group("base.group_system"):
                continue
            partner.tracking_emails_count = len(
                mt_obj._search([("recipient_address", "=", partner.email.lower())])
            )

    def email_bounced_set(self, tracking_emails, reason, event=None):
        res = super().email_bounced_set(tracking_emails, reason, event=event)
        self._email_bounced_set(reason, event)
        return res

    def _email_bounced_set(self, reason, event):
        for partner in self:
            if not partner.email:
                continue
            event = event or self.env["mail.activity.event"]
            event_str = (
                f'<a href="#" data-oe-model="mail.activity.event"'
                f'data-oe-id="{event.id or 0}">{event.id or _("unknown")}</a>'
            )
            body = _(
                "Email has been bounced: %(email)s\nReason: "
                "%(reason)s\nEvent: %(event_str)s",
                email=partner.email,
                reason=reason,
                event_str=event_str,
            )
            # This function can be called by the non user via the callback_method set in
            # /mail/tracking/mailgun/all/. A sudo() is not enough to succesfully send
            # the bounce message in this circumstances.
            if self.env.su:
                partner = partner.with_user(SUPERUSER_ID)
            partner.message_post(body=body)

    def check_email_validity(self):
        """
        Checks mailbox validity with Mailgun's API
        API documentation:
        https://documentation.mailgun.com/en/latest/api-email-validation.html
        """
        params = self.env["mail.activity.tracking"]._mailgun_values()
        timeout = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("mailgun.timeout", MAILGUN_TIMEOUT)
        )
        if not params.validation_key:
            raise UserError(
                _(
                    "You need to configure mailgun.validation_key"
                    " in order to be able to check mails validity"
                )
            )
        for partner in self.filtered("email"):
            res = requests.get(
                urljoin(params.api_url, "/v3/address/validate"),
                auth=("api", params.validation_key),
                params={"address": partner.email, "mailbox_verification": True},
                timeout=timeout,
            )
            if (
                not res
                or res.status_code != 200
                and not self.env.context.get("mailgun_auto_check")
            ):
                raise UserError(
                    _(
                        "Error %s trying to check mail" % res.status_code
                        or "of connection"
                    )
                )
            content = res.json()
            if "mailbox_verification" not in content:
                if not self.env.context.get("mailgun_auto_check"):
                    raise UserError(
                        _(
                            "Mailgun Error. Mailbox verification value wasn't"
                            " returned"
                        )
                    )
            # Not a valid address: API sets 'is_valid' as False
            # and 'mailbox_verification' as None
            if not content["is_valid"]:
                partner.email_bounced = True
                body = (
                    _(
                        "%s is not a valid email address. Please check it"
                        " in order to avoid sending issues"
                    )
                    % partner.email
                )
                if not self.env.context.get("mailgun_auto_check"):
                    raise UserError(body)
                partner.message_post(body=body)
            # If the mailbox is not valid API returns 'mailbox_verification'
            # as a string with value 'false'
            if content["mailbox_verification"] == "false":
                partner.email_bounced = True
                body = (
                    _(
                        "%s failed the mailbox verification. Please check it"
                        " in order to avoid sending issues"
                    )
                    % partner.email
                )
                if not self.env.context.get("mailgun_auto_check"):
                    raise UserError(body)
                partner.message_post(body=body)
            # If Mailgun can't complete the validation request the API returns
            # 'mailbox_verification' as a string set to 'unknown'
            if content["mailbox_verification"] == "unknown":
                if not self.env.context.get("mailgun_auto_check"):
                    raise UserError(
                        _(
                            "%s couldn't be verified. Either the request couln't"
                            " be completed or the mailbox provider doesn't "
                            "support email verification"
                        )
                        % (partner.email)
                    )

    def check_email_bounced(self):
        """
        Checks if the partner's email is listed in Mailgun's bounce suppression list.
        API documentation:
        https://documentation.mailgun.com/en/latest/api-suppressions.html
        """
        api_key, api_url, domain, *__ = self.env[
            "mail.activity.tracking"
        ]._mailgun_values()
        timeout = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("mailgun.timeout", MAILGUN_TIMEOUT)
        )
        for partner in self:
            res = requests.get(
                urljoin(api_url, f"/v3/{domain}/bounces/{partner.email}"),
                auth=("api", api_key),
                timeout=timeout,
            )
            if res.status_code == 200 and not partner.email_bounced:
                partner.email_bounced = True
            elif res.status_code == 404 and partner.email_bounced:
                partner.email_bounced = False

    def force_set_bounced(self):
        """
        Forces partner's email into Mailgun's bounces list
        API documentation:
        https://documentation.mailgun.com/en/latest/api-suppressions.html
        """
        api_key, api_url, domain, *__ = self.env[
            "mail.activity.tracking"
        ]._mailgun_values()
        timeout = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("mailgun.timeout", MAILGUN_TIMEOUT)
        )
        for partner in self:
            res = requests.post(
                urljoin(api_url, "/v3/{domain}/bounces"),
                auth=("api", api_key),
                data={"address": partner.email},
                timeout=timeout,
            )
            partner.email_bounced = res.status_code == 200 and not partner.email_bounced

    def force_unset_bounced(self):
        """
        Forcibly removes the partner's email from Mailgun's bounce suppression list.
        API documentation:
        https://documentation.mailgun.com/en/latest/api-suppressions.html
        """
        api_key, api_url, domain, *__ = self.env[
            "mail.activity.tracking"
        ]._mailgun_values()
        timeout = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("mailgun.timeout", MAILGUN_TIMEOUT)
        )
        for partner in self:
            res = requests.delete(
                urljoin(api_url, f"/v3/{domain}/bounces/{partner.email}"),
                auth=("api", api_key),
                timeout=timeout,
            )
            if res.status_code in (200, 404) and partner.email_bounced:
                partner.email_bounced = False
