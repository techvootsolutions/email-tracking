/** @odoo-module **/
const {Component, useState} = owl;

export class MessageTracking extends Component {
    static template = "mail_activity_tracking.MessageTracking";
    static props = ["message", "partner_trackings", "skip_track_links?"];
    setup() {
        this.message = useState(this.props.message);
        this.partner_trackings = useState(this.props.partner_trackings);
    }
    _onTrackingStatusClick(event) {
        var tracking_email_id = $(event.currentTarget).data("tracking");
        event.preventDefault();
        return this.env.services.action.doAction({
            type: "ir.actions.act_window",
            view_type: "form",
            view_mode: "form",
            res_model: "mail.activity.tracking",
            views: [[false, "form"]],
            target: "new",
            res_id: tracking_email_id,
        });
    }
}
