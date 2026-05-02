import requests
from fake_useragent import UserAgent
ua = UserAgent()

STOPS = [
	"Albany, NY", "Binghamton, NY", "Brockport, NY", "Buffalo, NY", "Cortland, NY",
	"Geneva, NY", "Hamilton, NY", "Ithaca, NY", "Morrisville, NY", "Niagara Falls, NY",
	"Oswego, NY", "Rochester, NY", "Syracuse, NY", "Syracuse Airport, NY", "Utica, NY",
	"Whitney Point, NY", "JFK Airport, NY", "La Guardia Airport, NY",
	"Resorts World Catskills - Monticello, NY",
	"Allentown - Wescosville, PA", "Bethlehem, PA", "Douglassville, PA", "Easton, PA",
	"Hellertown, PA", "Kutztown, PA", "Lancaster, PA", "Malvern, PA", "Mount Pocono, PA",
	"Pittsburgh, PA", "Pittston, PA", "Reading, PA", "Scranton, PA", "Slippery Rock, PA",
	"Tannersville, PA", "Wilkes-Barre, PA", "Fort Washington, PA", "King of Prussia, PA",
	"State College, PA", "East Stroudsburg, PA", "Sesame Place Langhorne, PA",
	"Philadelphia International Airport, PA", "Delaware Water Gap, PA",
	"Akshardham Temple Robbinsville, NJ", "Avalon, NJ", "Beach Haven - Long Beach Island, NJ",
	"Bridgewater, NJ", "Cape May, NJ", "Cherry Hill, NJ", "East Hanover, NJ",
	"East Windsor, NJ", "Forked River - Ocean County - Parkway Mile 76, NJ", "Fort Lee, NJ",
	"Galloway - Atlantic County - Parkway Mile 41, NJ", "Hamilton-Trenton, NJ", "Margate, NJ",
	"Monroe, NJ", "Paterson, NJ", "Piscataway, NJ", "Princeton, NJ", "Rockaway, NJ",
	"Sea Isle City Beach, NJ", "Six Flags Great Adventure, NJ",
	"South Amboy - Cheesequake, NJ", "Stone Harbor, NJ", "Surf City - Long Beach Island, NJ",
	"Ventnor, NJ", "Wildwood Boardwalk, NJ", "Woodbridge, NJ", "Newark Airport, NJ",
	"Caesars Casino - Atlantic City, NJ", "MetLife Stadium East Rutherford, NJ",
	"Resorts Casino - Atlantic City, NJ", "Tropicana Casino - Atlantic City, NJ",
	"Baltimore - Pikesville, MD", "Baltimore - Towson, MD", "Baltimore, MD",
	"Bethesda, MD", "Columbia, MD", "Frederick, MD", "Rockville, MD",
	"Alexandria, VA", "Arlington, VA", "Blacksburg, VA", "Charlottesville, VA",
	"Fredericksburg, VA", "Gainesville, VA", "Glen Allen, VA", "Harrisonburg, VA",
	"Manassas, VA", "Newport News, VA", "Norfolk, VA", "Radford, VA", "Richmond, VA",
	"Roanoke, VA", "Springfield, VA", "Sterling, VA", "Tysons, VA", "Vienna, VA",
	"Virginia Beach, VA", "Williamsburg, VA", "Dulles Airport, VA",
	"Dewey Beach, DE", "Dover, DE", "Wilmington - Christiana, DE",
	"Washington, DC",
	"Boston, MA", "Gillette Stadium Foxborough, MA", "Lee - Berkshires, MA",
	"Ludlow, MA", "Methuen - Lawrence, MA", "Worcester, MA",
	"Hartford, CT",
	"Providence, RI",
	"Columbus, OH", "Dayton, OH",
	"Bloomington, IN", "Lafayette, IN", "Terre Haute, IN",
	"Troy, IL",
	"Chesterfield, MO", "Richmond Heights, MO",
	"Breckenridge, CO", "Copper Mountain, CO", "Denver Airport, CO", "Frisco, CO", "Vail, CO",
	"Brampton, ON", "Kitchener, ON", "London, ON", "Milton, ON", "Mississauga, ON", "Toronto, ON",
]

def searchStops(q: str):
	q_lower = q.lower()
	return [stop for stop in STOPS if q_lower in stop.lower()]

# dest: New York, NY
# day: 05/03/2026
def search(originCity: str, destCity: str, day: str):
	r = requests.post(
		"https://api.ourbus.com/wsapi/v3/search/intercity/exact?client_id=1",
		headers={"User-agent": ua.random},
		json={"date": day, "dest": destCity, "page": 1, "pass_count": 1, "route_type": "L", "size": 12, "sort_criteria": "pick_time", "src": originCity, "strategy": ["datebar"], "trip_type": "O"}
	)
	if r.status_code != 200:
		return {"error": True, "msg": f"got a non-200 from upstream (HTTP {r.status_code})"}
	trips = []
	for trip in r.json().get("list", []):
		trips.append({
			"price": trip.get("pass_amount") + trip.get("booking_fee") + trip.get("facility_fee"),
			"depart_time": trip.get("src_stop_eta"),
			"arrive_time": trip.get("dest_stop_eta"),
			"duration": None,
			"stops": [],
		})
	trips.sort(key=lambda t: t["price"])
	return trips[:5]

if __name__ == "__main__":
	search("New York, NY", "Boston, MA", "05/04/2026")
