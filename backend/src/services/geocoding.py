"""Geocoding utilities for reverse geocoding coordinates to place names."""
from __future__ import annotations

import logging
import httpx
from typing import Optional

log = logging.getLogger(__name__)

# Nominatim (OpenStreetMap) API - free, no API key required
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"


async def reverse_geocode(lat: float, lon: float) -> Optional[str]:
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
                timeout=5.0
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


def reverse_geocode_sync(lat: float, lon: float) -> Optional[str]:
    """Synchronous version of reverse geocode for use in sync contexts.

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
                    "zoom": 10,  # City/town level
                    "addressdetails": 1,
                },
                headers={
                    "User-Agent": "Homebound-App/1.0 (safety app for outdoor activities)"
                },
                timeout=5.0
            )

            if response.status_code != 200:
                log.warning(f"Nominatim returned {response.status_code}")
                return None

            data = response.json()

            if not data:
                return None

            address = data.get("address", {})

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
                    if not components or address[key] != components[0]:
                        components.append(address[key])
                    break

            if not components:
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
