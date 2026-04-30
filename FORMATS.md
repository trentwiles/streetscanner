# City Name Formats

## Greyhound / Flixbus

Cities are converted to internal UUIDs before being sent to the API. In the `greyhound.py` file, there is a converter that queries a city in English and gets the UUID.

## PeterPan

Similar to Greyhound, PeterPan uses a UUID system. All stops and their respective UUIDs can be found at this [static URL](https://web.peterpanbus.net/api/schedules/destinations) and a function in the `peterpan.py` allows plaintext searches.

## Coachrun


## Ourbus

English plaintext city names are used (eg. New York, NY). Sourced from https://www.ourbus.com/stops

# Database Plan

Use a database that includes city names and their translations for each API. For instance:

### Cities table
---------------
| City | `string` |
| ID | `uuid` |
---------------

### Translations table
-------------------------
| Bus Company | `string` |
| Identifier | `string` |
| City | `FK` to cities.id |
