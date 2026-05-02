# Street Scanner

[Diagram](https://www.notion.so/trentwiles/Street-Scanner-Diagram-354b34a7509c80bda284eeb6c30beea0?source=copy_link)

## Sample User Request

Leave Days - Fridays, Saturdays
Return Days - Sundays, Mondays
Origin City - Boston, MA
Destination City - New York City, NY



## Flixbus / Greyhound Search API

GET https://global.api.flixbus.com/search/service/v4/search?from_city_id=eeff627f-2fda-4e75-8468-783d47955b3a&to_city_id=c0a47c54-53ea-46dc-984b-b764fc0b2fa9&departure_date=29.04.2026&products=%7B%22adult%22%3A1%7D&currency=USD&locale=en_US&search_by=cities&include_after_midnight_rides=1&disable_distribusion_trips=0&disable_global_trips=0&disable_trips=%5B%22AU%22%5D

Boston City ID: eeff627f-2fda-4e75-8468-783d47955b3a
New York City ID: c0a47c54-53ea-46dc-984b-b764fc0b2fa9
New Haven City ID: 193c0a59-90e7-494e-b196-fe387b385a22
