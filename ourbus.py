import requests
from fake_useragent import UserAgent
ua = UserAgent()

def searchStops(q: str):
	r = requests.get(
                headers={"User-agent": ua.random},
		"https://www.ourbus.com/stops"
	)
	
	if r.status_code != 200:
		return {"error": True, "msg": f"got a non-200 from upstream (HTTP {str(r.status_code})"}

	matches = []
	for stop in r.json()
		if q in stop:
			matches.append(stop)
	
	return matches

# dest: New York, NY
# day: 05/03/2026
def search(originCity: str, destCity: str, day: str):
	r = requests.post(
		"https://api.ourbus.com/wsapi/v3/search/intercity/exact?client_id=1",
		headers={"User-agent": ua.random},
		json={"date": day, "dest": destCity, "page": 1, "pass_count": 1, "route_type": "L", "size": 12, "sort_criteria": "pick_time", "src": originCity, "strategy": ["datebar"], "trip_type": "O"}
	)
	print(r.text)

	# sort by price, get the cheapest 5

	trips = []
	for trip in r.json():
		trips.append({
			"price": trip.get("pass_amount") + trip.get("booking_fee") + trip.get("facility_fee"),
			"depart_time": trip.get("src_stop_eta"),
			"arrive_time": trip.get("dest_stop_eta"),
			"duration": None,
			"stops": [],
		})
	trips.sort(key=lambda t: t["price"])
	return trips

search("New York, NY", "Boston, MA", "05/04/2026")
