from odoo import models


class MailGuest(models.Model):
    _inherit = "mail.guest"

    def _init_messaging(self):
        """For discuss"""
        values = super()._init_messaging()
        values["failed_counter"] = False
        return values
