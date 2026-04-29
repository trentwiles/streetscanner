import requests
from fake_useragent import UserAgent
ua = UserAgent()

def searchCity(q: str):
	r = requests.get("https://web.peterpanbus.net/api/schedules/destinations", headers={"User-agent": ua.random})
	if r.status_code != 200:
		return {"error": True, "msg": f"got a non-200 from upstream (HTTP {str(r.status_code)}"}

	results = []
	for stop in r.json():
		if q in stop["stationName"]:
			results.append({"name": stop["displayText"], "verbose_name": stop["stationName"], "pp_id": stop["stopUuid"]})

	return results

print(searchCity("New"))
print(searchCity("Bos"))
