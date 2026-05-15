"""
Seed the cities and translations tables from all four carriers.

Run order:
  1. Coachrun  — smallest focused list, becomes the seed set of canonical cities
  2. Ourbus    — plaintext stops; exact matches add translations, new cities are added too
  3. PeterPan  — static endpoint; match by city.name + state.abbreviation
  4. Greyhound — live autocomplete per city; match on city name

Not every carrier serves every city — missing translations are expected and logged.
"""

import time
import requests
from fake_useragent import UserAgent

from db import init_db, add_city, get_city, add_translation, list_cities

ua = UserAgent()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _city_key(name: str) -> str:
    """'Boston, MA' -> 'boston ma'  (lowercase, no punctuation, for loose matching)"""
    return name.lower().replace(",", "").replace(".", "").strip()


def _first_word(name: str) -> str:
    """'New York, NY' -> 'new york'"""
    return name.split(",")[0].strip().lower()


# ---------------------------------------------------------------------------
# 1. Coachrun
# ---------------------------------------------------------------------------

COACHRUN_CITIES = [
    "Binghamton, NY", "Boston, MA", "Buffalo, NY", "Charlotte, NC",
    "Christiansburg, VA", "Colonial Heights, VA", "Cookeville, TN",
    "Dover, DE", "Durham, NC", "Fredericksburg, VA", "Greensboro, NC",
    "Hampton, VA", "Harrisonburg, VA", "Johnson City, TN", "Knoxville, TN",
    "Liverpool, NY", "Millbury, MA", "Baltimore, MD", "Nashville, TN",
    "New York, NY", "Norfolk, VA", "Philadelphia, PA", "Raleigh, NC",
    "Richmond, VA", "Roanoke, VA", "Rochester, NY", "Salisbury, MD",
    "Syracuse, NY", "Virginia Beach, VA", "Washington, DC", "Worcester, MA",
]


def seed_coachrun():
    print("\n=== Coachrun ===")
    for name in COACHRUN_CITIES:
        city_id = add_city(name)
        add_translation(city_id, "coachrun", name)
        print(f"  + {name}")
    print(f"  {len(COACHRUN_CITIES)} cities seeded")


# ---------------------------------------------------------------------------
# 2. Ourbus
# ---------------------------------------------------------------------------

OURBUS_STOPS = [
    "Albany, NY", "Binghamton, NY", "Brockport, NY", "Buffalo, NY", "Cortland, NY",
    "Geneva, NY", "Hamilton, NY", "Ithaca, NY", "Morrisville, NY", "Niagara Falls, NY",
    "Oswego, NY", "Rochester, NY", "Syracuse, NY", "Syracuse Airport, NY", "Utica, NY",
    "New York, NY", "Whitney Point, NY", "JFK Airport, NY", "La Guardia Airport, NY",
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

# Stops whose name doesn't match a canonical "City, ST" but map to one we already have.
# Key: ourbus stop string  ->  canonical city name
OURBUS_OVERRIDES = {
    "Baltimore - Pikesville, MD": "Baltimore, MD",
    "Baltimore - Towson, MD":     "Baltimore, MD",
    "Philadelphia International Airport, PA": "Philadelphia, PA",
    "Syracuse Airport, NY":       "Syracuse, NY",
}


def seed_ourbus():
    print("\n=== Ourbus ===")
    matched = skipped = added = 0
    for stop in OURBUS_STOPS:
        canonical = OURBUS_OVERRIDES.get(stop, stop)
        city = get_city(canonical)
        if city:
            add_translation(city["id"], "ourbus", stop)
            print(f"  ~ {stop}  ->  {canonical}")
            matched += 1
        else:
            # New city not in Coachrun — add it
            city_id = add_city(canonical)
            add_translation(city_id, "ourbus", stop)
            print(f"  + {stop}  (new)")
            added += 1
    print(f"  matched={matched}  new={added}  skipped={skipped}")


# ---------------------------------------------------------------------------
# 3. PeterPan
# ---------------------------------------------------------------------------

def seed_peterpan():
    print("\n=== PeterPan ===")
    r = requests.get(
        "https://web.peterpanbus.net/api/schedules/destinations",
        headers={"User-Agent": ua.random},
    )
    if r.status_code != 200:
        print(f"  ERROR: HTTP {r.status_code}")
        return

    all_stops = r.json()

    # Build lookup: "City, ST" -> list of stops (prefer peterpan:true)
    pp_by_city: dict[str, list] = {}
    for stop in all_stops:
        city_name = stop.get("city", {}).get("name", "")
        state_abbr = stop.get("state", {}).get("abbreviation", "")
        if not city_name or not state_abbr:
            continue
        key = f"{city_name}, {state_abbr}"
        pp_by_city.setdefault(key, []).append(stop)

    matched = skipped = 0
    for city in list_cities():
        candidates = pp_by_city.get(city["name"])
        if not candidates:
            print(f"  - {city['name']}  (no PeterPan stop)")
            skipped += 1
            continue

        # Prefer stops flagged peterpan:true, then take the first
        pp_only = [s for s in candidates if s.get("peterpan")]
        chosen = (pp_only or candidates)[0]
        add_translation(city["id"], "peterpan", chosen["stopUuid"])
        print(f"  + {city['name']}  ->  {chosen['stationName']}  ({chosen['stopUuid']})")
        matched += 1

    print(f"  matched={matched}  skipped={skipped}")


# ---------------------------------------------------------------------------
# 4. Greyhound / Flixbus
# ---------------------------------------------------------------------------

GH_AUTOCOMPLETE = (
    "https://global.api.flixbus.com/search/autocomplete/cities"
    "?q={q}&lang=en_US&country=us&flixbus_cities_only=false&is_train_only=false"
    "&stations=false&popular_stations_count=null&disabled_countries=AU"
)

# Canonical name -> Greyhound UUID, for cities whose names don't survive the state filter
GH_DIRECT = {
    "New York, NY":  "c0a47c54-53ea-46dc-984b-b764fc0b2fa9",  # "New York, NY" via "New York City" query
    "Washington, DC": "adcc1f7d-3bfe-471d-9946-28253814a09b", # "Washington, D.C." (D.C. ≠ DC filter)
}


def _gh_search(q: str) -> list[dict]:
    r = requests.get(GH_AUTOCOMPLETE.format(q=q), headers={"User-Agent": ua.random})
    if r.status_code != 200:
        return []
    return [c for c in r.json() if c.get("country") == "us"]


def _state_from_canonical(name: str) -> str:
    """'Boston, MA' -> 'MA'"""
    parts = name.rsplit(",", 1)
    return parts[1].strip() if len(parts) == 2 else ""


def seed_greyhound():
    print("\n=== Greyhound / Flixbus ===")
    matched = skipped = 0
    for city in list_cities():
        canonical = city["name"]
        state = _state_from_canonical(canonical)

        # Hard-coded UUID for cities where name normalization can't find them
        if canonical in GH_DIRECT:
            add_translation(city["id"], "greyhound", GH_DIRECT[canonical])
            print(f"  + {canonical}  ->  (direct override)")
            matched += 1
            continue

        # Skip non-US cities (Canadian provinces, etc.)
        if not state or len(state) != 2:
            print(f"  - {canonical}  (skipping non-US city)")
            skipped += 1
            continue

        query = canonical.split(",")[0].strip()
        results = _gh_search(query)

        # Filter to results that contain the correct state abbreviation
        state_results = [c for c in results if f", {state}" in c["name"]]

        # Exact match first, then startswith within the state-filtered set
        canonical_lower = canonical.lower()
        hit = next((c for c in state_results if c["name"].lower() == canonical_lower), None)
        if not hit:
            city_part = query.lower()
            hit = next((c for c in state_results if c["name"].lower().startswith(city_part)), None)

        if hit:
            add_translation(city["id"], "greyhound", hit["id"])
            print(f"  + {canonical}  ->  {hit['name']}  ({hit['id']})")
            matched += 1
        else:
            print(f"  - {canonical}  (no Greyhound match)")
            skipped += 1

        time.sleep(0.15)  # be polite

    print(f"  matched={matched}  skipped={skipped}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    seed_coachrun()
    seed_ourbus()
    seed_peterpan()
    seed_greyhound()

    cities = list_cities()
    print(f"\nDone. {len(cities)} total cities in DB.")
