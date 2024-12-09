from odoo import api, fields, models


class CRMLead(models.Model):
    _inherit = "crm.lead"

    mail_status = fields.Selection(related='mail_activity_tracking_id.state', string="Mail State", store=True)
    mail_activity_tracking_id = fields.Many2one('mail.activity.tracking', string="Mail Activity Tracking")


class MailTrackingEmail(models.Model):
    _inherit = "mail.activity.tracking"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if self._context.get('res_model') and self._context.get('res_model') in ('crm.lead') and self._context.get('record_id'):
            record_id = self.env[self._context.get('res_model')].browse(self._context.get('record_id'))
            record_id.update({'mail_activity_tracking_id': records.id})
        return records
