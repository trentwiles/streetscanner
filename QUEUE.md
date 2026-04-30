# Jobs Queue

When a user submits a request to recieve emails on bus ticket prices, their request will be entered into queue table in the database.

It might look something like this:

----------------
| request_id | `uuid` |
| email | `string` |
| submit_ip | `string` |
| submit_time | `string` |
| submit_user_agent | `string` |
| originCity | `string` `FK` to `cities.city` |
| destCity | `string` `FK` to `cities.city` |
-----------------

A cronjob will iterate through all jobs in the DB at a given time and find the cheapest bus tickets in the next 4-8 weeks.
