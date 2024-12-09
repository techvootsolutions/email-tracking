from email.utils import getaddresses

from lxml import etree

from odoo import _, api, fields, models
from odoo.tools import email_split, email_split_and_format


class MailThread(models.AbstractModel):
    _inherit = "mail.thread"

    failed_message_ids = fields.One2many(
        "mail.message",
        "res_id",
        string="Failed Messages",
        domain=lambda self: [("model", "=", self._name)]
        + self._get_failed_message_domain(),
    )

    def _get_message_create_valid_field_names(self):
        valid_field_names = super()._get_message_create_valid_field_names()
        return valid_field_names | {"email_to", "email_cc"}

    def _get_failed_message_domain(self):
        """
            Domain used to display failed messages in the 'failed_messages' widget.
        """
        failed_states = self.env["mail.message"].get_failed_states()
        return [
            ("mail_tracking_needs_action", "=", True),
            ("mail_tracking_ids.state", "in", list(failed_states)),
        ]

    @api.model
    def _message_route_process(self, message, message_dict, routes):
        """
            Adds a CC recipient to the message.

            Odoo's implementation does not store 'from', 'to', or 'cc' recipients directly. 
            This ensures that the CC recipient is recorded in the mail.message record.
        """
        message_dict.update(
            {
                "email_cc": message_dict.get("cc", False),
                "email_to": message_dict.get("to", False),
            }
        )
        return super()._message_route_process(message, message_dict, routes)

    def _routing_handle_bounce(self, email_message, message_dict):
        bounced_message = message_dict["bounced_message"]
        mail_trackings = bounced_message.mail_tracking_ids.filtered(
            lambda x: x.recipient_address == message_dict["bounced_email"]
            or (
                message_dict["bounced_partner"]
                and message_dict["bounced_partner"] == x.partner_id
            )
        )
        if mail_trackings:
            # TODO detect hard of soft bounce
            mail_trackings.event_create("soft_bounce", message_dict)
        return super()._routing_handle_bounce(email_message, message_dict)

    def _message_get_suggested_recipients(self):
        """
            Adds 'extra' recipients as suggested recipients.

            If the recipient is associated with a res.partner, it will be used.
        """
        res = super()._message_get_suggested_recipients()
        self._add_extra_recipients_suggestions(res, "email_cc", _("Cc"))
        self._add_extra_recipients_suggestions(res, "email_to", _("Anon. To"))
        return res

    def _add_extra_recipients_suggestions(self, suggestions, field_mail, reason):
        """
            Adds extra recipients as suggested recipients for the email.

            This function processes additional email recipients and, if they are linked to a `res.partner`, associates them accordingly. The recipients are then marked as suggested recipients for the email.

            If a recipient has an associated `res.partner` record, it will be utilized to enhance recipient suggestions.

            Returns:
                None
        """
        ResPartnerObj = self.env["res.partner"]
        aliases = self.env["mail.alias"].get_aliases()
        email_extra_formated_list = []
        for record in self:
            emails_extra = record.message_ids.mapped(field_mail)
            for email in emails_extra:
                email_extra_formated_list.extend(email_split_and_format(email))
        email_extra_formated_list = set(email_extra_formated_list)
        email_extra_list = [x[1] for x in getaddresses(email_extra_formated_list)]
        partners_info = self.sudo()._message_partner_info_from_emails(email_extra_list)
        for pinfo in partners_info:
            partner_id = pinfo["partner_id"]
            email_formed = email_split(pinfo["full_name"])
            email = email_formed and email_formed[0].lower()
            if not partner_id:
                if email not in aliases:
                    self._message_add_suggested_recipient(
                        suggestions, email=email, reason=reason
                    )
            else:
                partner = ResPartnerObj.browse(partner_id)
                self._message_add_suggested_recipient(
                    suggestions, partner=partner, reason=reason
                )

    @api.model
    def get_view(self, view_id=None, view_type="form", **options):
        """
            Adds filters for failed messages.

            These filters will be available in the search views of any model that inherits from ``mail.thread``, allowing users to filter and view messages marked as failed.

            This functionality enables better management and visibility of failed messages across various mail-related models.
        """
        res = super().get_view(view_id, view_type, **options)
        if view_type != "search":
            return res
        doc = etree.XML(res["arch"])
        # Modify view to add new filter element
        nodes = doc.xpath("//search")
        if nodes:
            # Create filter element
            new_filter = etree.Element(
                "filter",
                {
                    "string": _("Failed sent messages"),
                    "name": "failed_message_ids",
                    "domain": str(
                        [
                            [
                                "failed_message_ids.mail_tracking_ids.state",
                                "in",
                                list(self.env["mail.message"].get_failed_states()),
                            ],
                            [
                                "failed_message_ids.mail_tracking_needs_action",
                                "=",
                                True,
                            ],
                        ]
                    ),
                },
            )
            nodes[0].append(etree.Element("separator"))
            nodes[0].append(new_filter)
        res["arch"] = etree.tostring(doc, encoding="unicode")
        return res
