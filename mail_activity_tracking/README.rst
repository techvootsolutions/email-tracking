=======================
Email activity tracking
=======================

This module shows email notification tracking status for any messages in
mail thread (chatter). Each notified partner will have an intuitive icon
just right to his name.

**Table of contents**

.. contents::
   :local:

Installation
============

If you're using a multi-database installation (with or without dbfilter
option) where /web/databse/selector returns a list of more than one
database, then you need to add ``mail_activity_tracking`` addon to wide load
addons list (by default, only ``web`` addon), setting ``--load`` option.
For example, ``--load=web,mail,mail_activity_tracking``

Configuration
=============

As there can be scenarios where sending a tracking img in the email body
is not desired, there is a global system parameter
"mail_activity_tracking.tracking_img_disabled" that can be set to True to remove
the tracking img from all outgoing emails. Note that the **Opened**
status will not be available in this case.

Usage
=====

When user sends a message in mail_thread (chatter), for instance in
partner form, then an email tracking is created for each email
notification. Then a status icon will appear just right to name of
notified partner.

These are all available status icons:

|unknown| **Unknown**: No email tracking info available. Maybe this
notified partner has 'Receive Inbox Notifications by Email' == 'Never'

|waiting| **Waiting**: Waiting to be sent

|error| **Error**: Error while sending

|sent| **Sent**: Sent to SMTP server configured

|delivered| **Delivered**: Delivered to final MX server

|opened| **Opened**: Opened by partner

|cc| **Cc**: It's a Carbon-Copy recipient. Can't know the status so is
'Unknown'

|noemail| **No Email**: The partner doesn't have a defined email

|anonuser| **No Partner**: The recipient doesn't have a defined partner

If you want to see all tracking emails and events you can go to

-  Settings > Technical > Email > Tracking emails
-  Settings > Technical > Email > Tracking events

When a message generated an 'sent' status. In any view with chatter can show the messages too.

-  Sent

   |sent_img|

When a message moved on 'delivered' status.

-  Delivered

   |delivered_img|

When a message moved on 'opened' status.

-  Opened

   |opened_img|

When the message generates an ‘error’ status, it will apear on discuss
‘Failed’ channel. Any view with chatter can also display failed messages.

-  Discuss

   |failed_msg|

-  Chatter
   
   |rejected_img|

Display mail status in list view.

- Mail State

   |mail_state|

.. |unknown| image:: /mail_activity_tracking/static/img/unknown.png
.. |waiting| image:: /mail_activity_tracking/static/img/waiting.png
.. |error| image:: /mail_activity_tracking/static/img/error.png
.. |sent| image:: /mail_activity_tracking/static/img/sent.png
.. |delivered| image:: /mail_activity_tracking/static/img/delivered.png
.. |opened| image:: /mail_activity_tracking/static/img/opened.png
.. |cc| image:: /mail_activity_tracking/static/img/cc.png
   :width: 20px
   :height: 20px
.. |noemail| image:: /mail_activity_tracking/static/img/noemail.png
   :width: 20px
   :height: 20px
.. |anonuser| image:: /mail_activity_tracking/static/img/anon_user.png
.. |sent_img| image:: /mail_activity_tracking/static/img/sent_img.png
.. |delivered_img| image:: /mail_activity_tracking/static/img/delivered_img.png
.. |opened_img| image:: /mail_activity_tracking/static/img/opened_img.png
.. |failed_msg| image:: /mail_activity_tracking/static/img/failed_msg.png
.. |rejected_img| image:: /mail_activity_tracking/static/img/rejected_img.png
.. |mail_state| image:: /mail_activity_tracking/static/img/mail_state_list_view.png


Credits
=======

Authors
-------

* Techvoot Solutions

Contributors
------------

-  `Techvoot Solutions <https://www.techvoot.com>`__:

   -  Kevin Baldha
   -  Dhaval Baldha

Maintainers
-----------

This module is maintained by the Techvoot Solutions.

.. image:: /mail_activity_tracking/static/img/tv-logo-white.svg
   :alt: Techvoot Solutions
   :target: https://www.techvoot.com
