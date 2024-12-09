from odoo import models


class ResUsers(models.Model):
    _inherit = "res.users"

    def _init_messaging(self):
        values = super()._init_messaging()
        values["failed_counter"] = self.env["mail.message"].get_failed_count()
        return values
