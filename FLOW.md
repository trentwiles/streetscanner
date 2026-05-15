# Trip Request Lifecycle

1. The user accesses the form to create a notification of trips on certain days, between two fixed locations
2. The request is added to the database with an "unverified" flag/boolean
3. After submitting the request, the user is prompted to validate the request by clicking on a link in their email; they will be encouraged to check their spam and whitelist the sender
4. The unverified flag/boolean on the existing request is switched to verified
5. A cronjob inspects the requests in the database, and fufils them by scraping the coresponding bus company website(s), sending findings to the database, and then adding the discovered emails to a database with a tag for what request they correspond to
6. Another cronjob inspects the bus trips discovered in the database, and at a given interval, takes all trips found for a user, bundles them into an email, and sends it off
7. The user will recieve the email containing all trip times; with links to view trips and subscription status
8. Upon a click of these links, with a unique token embeded into their query strings, the user will be brought to a site page that lists out all trips that the system has found, and options to unsubscribe from bus trip notifications (users can have multiple scans and trips)
