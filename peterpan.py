import requests
import json
from fake_useragent import UserAgent
ua = UserAgent()

BASE_URL = "https://ride-api.peterpanbus.com/tickets"
BASE_HEADERS = {
    "TDS-Carrier-Code": "PPB",
    "TDS-Api-Key": "8FEE8AD4-82EA-436D-905D-DA9E8E5EC9D4",
    "Content-Type": "application/json",
}

def searchCity(q: str):
    r = requests.get("https://web.peterpanbus.net/api/schedules/destinations", headers={"User-agent": ua.random})
    if r.status_code != 200:
        return {"error": True, "msg": f"got a non-200 from upstream (HTTP {str(r.status_code)}"}

    results = []
    for stop in r.json():
        if q in stop["stationName"]:
            results.append({"name": stop["displayText"], "verbose_name": stop["stationName"], "pp_id": stop["stopUuid"]})

    return results

def search(fromUUID: str, toUUID: str, departDate: str):
    r = requests.post(
        f"{BASE_URL}/v3/schedule",
        headers={**BASE_HEADERS, "User-Agent": ua.random},
        json={
            "purchaseType": "SCHEDULE_BOOK",
            "origin": {"stopUuid": fromUUID},
            "destination": {"stopUuid": toUUID},
            "departDate": departDate,
            "cityMode": False,
            "isReturn": False,
            "passengerCounts": {"Adult": 1, "Military": 0, "Senior": 0, "Student": 0, "Child": 0},
            "fareSearchInformation": {
                "outboundSpecialFareId": None,
                "outboundTravelDate": departDate,
                "returningSearch": False,
                "returningTravelDate": None,
            },
        },
    )

    if r.status_code != 200:
        return {"error": True, "msg": f"got a non-200 from upstream (HTTP {r.status_code})"}

    def min_fare(product):
        try:
            fares = product["railgunFares"]["Adult"][0]["fares"]
            return min(f["amount"] for f in fares)
        except (KeyError, IndexError, ValueError):
            return float("inf")

    products = r.json().get("scheduleProducts", [])

    def extract_stops(segments):
        if not segments:
            return []
        stops = [{"name": segments[0]["departStop"]["stationName"], "time": segments[0]["departTime"]}]
        for seg in segments:
            stops.append({"name": seg["arriveStop"]["stationName"], "time": seg["arriveTime"]})
        return stops

    cleaned = []
    for trip in sorted(products, key=min_fare)[:5]:
        run = trip.get("scheduleRun", {})
        segments = trip.get("segments", [])
        cleaned.append({
            "price": min_fare(trip),
            "depart_time": run.get("departTime"),
            "arrive_time": run.get("arriveTime"),
            "duration": run.get("travelDuration"),
            "stops": extract_stops(segments),
        })

    return json.dumps(cleaned)

if __name__ == "__main__":
    result = search("ff873135-3313-45f9-99fd-8f1c1be9a3a2", "31489613-da82-4b96-97c3-c75415f63ba0", "2026-05-01")
    print(result)
