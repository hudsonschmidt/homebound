"""Geocoding utilities for reverse geocoding coordinates to place names."""
from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)

# Nominatim (OpenStreetMap) API - free, no API key required
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"


async def reverse_geocode(lat: float, lon: float) -> str | None:
    """Reverse geocode coordinates to a human-readable location name.

    Returns a broad location like city, park, or region name.
    Falls back to None if geocoding fails.

    Args:
        lat: Latitude
        lon: Longitude

    Returns:
        Human-readable location string or None
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                NOMINATIM_URL,
                params={
                    "lat": lat,
                    "lon": lon,
                    "format": "json",
                    "zoom": 10,  # City/town level - broader results
                    "addressdetails": 1,
                },
                headers={
                    "User-Agent": "Homebound-App/1.0 (safety app for outdoor activities)"
                },
                timeout=10.0
            )

            if response.status_code != 200:
                log.warning(f"Nominatim returned {response.status_code}")
                return None

            data = response.json()

            if not data:
                return None

            # Try to build a meaningful location name
            address = data.get("address", {})

            # Priority order for location components (prefer natural features and landmarks)
            # Look for natural features first (parks, forests, mountains, etc.)
            natural_keys = [
                "natural",
                "leisure",  # parks, nature reserves
                "landuse",
                "tourism",  # viewpoints, attractions
            ]

            for key in natural_keys:
                if key in address and address[key]:
                    # Return the natural feature name if available
                    if "name" in data and data["name"]:
                        return data["name"]

            # Build location from address components
            components = []

            # Try to get a named place first
            place_keys = [
                "hamlet",
                "village",
                "town",
                "city",
                "municipality",
            ]

            for key in place_keys:
                if key in address and address[key]:
                    components.append(address[key])
                    break

            # Add county/region for context
            region_keys = ["county", "state_district", "state", "region"]
            for key in region_keys:
                if key in address and address[key]:
                    # Don't duplicate if same as place
                    if not components or address[key] != components[0]:
                        components.append(address[key])
                    break

            # If we still have nothing, try the display_name but truncate it
            if not components:
                display_name = data.get("display_name", "")
                if display_name:
                    # Take first 2-3 parts of the address
                    parts = display_name.split(", ")[:3]
                    return ", ".join(parts)
                return None

            return ", ".join(components)

    except httpx.TimeoutException:
        log.warning(f"Geocoding timeout for ({lat}, {lon})")
        return None
    except Exception as e:
        log.warning(f"Geocoding error for ({lat}, {lon}): {e}")
        return None


def reverse_geocode_sync(lat: float, lon: float) -> str | None:
    """Synchronous version of reverse geocode for use in sync contexts.

    Returns precise address or POI name (e.g., "123 Main St, San Francisco, CA").

    Args:
        lat: Latitude
        lon: Longitude

    Returns:
        Human-readable location string or None
    """
    try:
        with httpx.Client() as client:
            response = client.get(
                NOMINATIM_URL,
                params={
                    "lat": lat,
                    "lon": lon,
                    "format": "json",
                    "zoom": 18,  # Building level - maximum precision
                    "addressdetails": 1,
                },
                headers={
                    "User-Agent": "Homebound-App/1.0 (safety app for outdoor activities)"
                },
                timeout=10.0
            )

            if response.status_code != 200:
                log.warning(f"Nominatim returned {response.status_code}")
                return None

            data = response.json()

            if not data:
                return None

            address = data.get("address", {})
            components = []

            # Priority 1: POI/Amenity name (parks, businesses, landmarks)
            poi_keys = ["amenity", "tourism", "leisure", "shop", "building"]
            poi_name = None
            for key in poi_keys:
                if key in address and address[key]:
                    # The POI name is often in the top-level "name" field
                    if data.get("name"):
                        poi_name = data["name"]
                        break

            if poi_name:
                components.append(poi_name)
            else:
                # Priority 2: Street address (house number + road)
                road = address.get("road") or address.get("pedestrian") or address.get("path")
                house_number = address.get("house_number")

                if road:
                    if house_number:
                        components.append(f"{house_number} {road}")
                    else:
                        components.append(road)
                else:
                    # Priority 3: Neighborhood/Suburb
                    neighborhood = address.get("neighbourhood") or address.get("suburb") or address.get("quarter")
                    if neighborhood:
                        components.append(neighborhood)

            # Add city for context
            city = (address.get("city") or address.get("town") or
                    address.get("village") or address.get("municipality"))
            if city and (not components or city not in components[0]):
                components.append(city)

            # Add state abbreviation or name
            state = address.get("state")
            if state:
                # Use common abbreviations for US states
                state_abbrevs = {
                    "California": "CA", "New York": "NY", "Texas": "TX",
                    "Florida": "FL", "Washington": "WA", "Oregon": "OR",
                    "Colorado": "CO", "Arizona": "AZ", "Nevada": "NV",
                    "Utah": "UT", "Montana": "MT", "Idaho": "ID",
                    "Wyoming": "WY", "New Mexico": "NM", "Alaska": "AK",
                    "Hawaii": "HI", "Pennsylvania": "PA", "Illinois": "IL",
                    "Ohio": "OH", "Georgia": "GA", "North Carolina": "NC",
                    "Michigan": "MI", "New Jersey": "NJ", "Virginia": "VA",
                    "Massachusetts": "MA", "Tennessee": "TN", "Indiana": "IN",
                    "Missouri": "MO", "Maryland": "MD", "Wisconsin": "WI",
                    "Minnesota": "MN", "South Carolina": "SC", "Alabama": "AL",
                    "Louisiana": "LA", "Kentucky": "KY", "Oklahoma": "OK",
                    "Connecticut": "CT", "Iowa": "IA", "Mississippi": "MS",
                    "Arkansas": "AR", "Kansas": "KS", "Nebraska": "NE",
                    "West Virginia": "WV", "New Hampshire": "NH", "Maine": "ME",
                    "Rhode Island": "RI", "Delaware": "DE", "South Dakota": "SD",
                    "North Dakota": "ND", "Vermont": "VT", "District of Columbia": "DC",
                }
                state_abbrev = state_abbrevs.get(state, state)
                components.append(state_abbrev)

            if not components:
                # Fallback: use display_name truncated
                display_name = data.get("display_name", "")
                if display_name:
                    parts = display_name.split(", ")[:3]
                    return ", ".join(parts)
                return None

            return ", ".join(components)

    except httpx.TimeoutException:
        log.warning(f"Geocoding timeout for ({lat}, {lon})")
        return None
    except Exception as e:
        log.warning(f"Geocoding error for ({lat}, {lon}): {e}")
        return None
