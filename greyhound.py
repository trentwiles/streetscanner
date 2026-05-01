import requests
from fake_useragent import UserAgent
ua = UserAgent()

import urllib.parse

# scraper code for greyhound / flixbus

BASE_URL = "https://global.api.flixbus.com/search"
COMMON_CITIES = {
	"Boston": "eeff627f-2fda-4e75-8468-783d47955b3a",
	"New York City": "c0a47c54-53ea-46dc-984b-b764fc0b2fa9"
}


# get the ID of a flixbus/greyhound stop
def searchCity(q: str):
	r = requests.get(
		f"{BASE_URL}/autocomplete/cities?q={q}&lang=en_US&country=us&flixbus_cities_only=false&is_train_only=false&stations=false&&popular_stations_count=null&disabled_countries=AU",
		headers={"User-agent": ua.random}
	)
	print(r.json())

	if r.status_code != 200:
		return {'error': True, 'msg': f'got a non-200 from upstream (HTTP {str(r.status_code)}'}

	valid_cities = []
	for city in r.json():
		if city['country'] != 'us':
			continue
		valid_cities.append({'name': city['name'], 'gh_id': city['id']})

	return valid_cities

def _generateFrontendSearchURL(fromCity: str, toCity: str, depart: str):
	return f"https://shop.greyhound.com/search?departureCity={fromCity}&arrivalCity={toCity}&rideDate={depart}&adult=1&_locale=en_US&departureCountryCode=US&arrivalCountryCode=US"

# fromCity and toCity should both be greyhound IDs that can be queried using the function above
def searchTrip(fromCity: str, toCity: str, depart: str):
	products = urllib.parse.quote_plus('{"adult":1}')
	disable_locales = urllib.parse.quote_plus('["AU"]')
	r = requests.get(
		f"{BASE_URL}/service/v4/search?from_city_id={fromCity}&to_city_id={toCity}&departure_date={depart}&products={products}&currency=USD&locale=en_US&search_by=cities&include_after_midnight_rides=1&disable_distribusion_trips=0&disable_global_trips=0&disable_trips={disable_locales}"
	)

	if r.status_code != 200:
                return {'error': True, 'msg': f'got a non-200 from upstream (HTTP {str(r.status_code)}'}

	# pull the 5 (or less) cheapest trips
	cheapest_trips = []
	results = r.json()['trips'][0]['results']
	for result in results.values():
		if result.get('status') != 'available':
			continue
		cheapest_trips.append({
			'departure': result['departure']['date'],
			'arrival': result['arrival']['date'],
			'duration_hours': result['duration']['hours'],
			'duration_minutes': result['duration']['minutes'],
			'price_usd': result['price']['total'],
			'transfer_type': result['transfer_type'],
			'seats_available': result['available']['seats'],
		})

	cheapest_trips.sort(key=lambda t: t['price_usd'])
	return {"frontend_url": _generateFrontendSearchURL(fromCity, toCity, depart), "options": cheapest_trips[:5]}


if __name__ == "__main__":
	print(searchTrip("eeff627f-2fda-4e75-8468-783d47955b3a", "c0a47c54-53ea-46dc-984b-b764fc0b2fa9", "29.04.2026"))
