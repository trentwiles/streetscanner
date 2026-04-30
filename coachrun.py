import re
import requests
from fake_useragent import UserAgent
ua = UserAgent()

BASE_URL = "https://www.coachrun.com/bus/search"

# Cities available: see b_cities in /js/aff/bus_search_source1350154.js
# e.g. "New York, NY", "Boston, MA", "Washington, DC", "Philadelphia, PA", etc.

def search(fromCity: str, toCity: str, departDate: str):
    r = requests.get(
        BASE_URL,
        params={
            "departureCity": fromCity,
            "arrivalCity": toCity,
            "departureDate": departDate,  # YYYY-MM-DD
            "adult": 1,
            "child": 0,
            "client": "1350154",
            "target": "1350154",
        },
        headers={"User-Agent": ua.random},
    )

    if r.status_code != 200:
        return {"error": True, "msg": f"got a non-200 from upstream (HTTP {r.status_code})"}

    trips = []
    for row in re.split(r'(?=<tr[^>]+name="table_radselect")', r.text):
        pid_m = re.search(r'pid="(\d+)"', row)
        if not pid_m:
            continue
        dep_m = re.search(r'name="departure" value="([^"]+)"', row)
        arr_m = re.search(r'name="arrival" value="([^"]+)"', row)
        dur_m = re.search(r'class="dur-text[^"]*"[^>]*>([^<]+)', row)
        price_m = re.search(r'\$(\d+)<sup>\.(\d+)</sup>', row)

        trips.append({
            "price": float(price_m.group(1) + "." + price_m.group(2)) if price_m else None,
            "departure": dep_m.group(1) if dep_m else None,
            "arrival": arr_m.group(1) if arr_m else None,
            "duration": dur_m.group(1).strip() if dur_m else None,
            "pid": pid_m.group(1),
        })

    trips.sort(key=lambda t: (t["price"] is None, t["price"]))
    return trips[:5]


result = search("New York, NY", "Boston, MA", "2026-05-01")
for t in result:
    print(t)
