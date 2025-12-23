"""Tests for geocoding utilities."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from src.services.geocoding import reverse_geocode, reverse_geocode_sync


class TestReverseGeocode:
    """Tests for async reverse geocoding."""

    @pytest.mark.asyncio
    async def test_reverse_geocode_success_with_name(self):
        """Test successful geocoding with location name."""
        mock_response = {
            "name": "Yosemite National Park",
            "address": {
                "leisure": "park",
                "county": "Mariposa County",
                "state": "California"
            }
        }

        with patch("src.services.geocoding.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_response
            mock_instance.get.return_value = mock_resp

            result = await reverse_geocode(37.7456, -119.5936)

            assert result == "Yosemite National Park"

    @pytest.mark.asyncio
    async def test_reverse_geocode_success_with_city(self):
        """Test geocoding returns city and region."""
        mock_response = {
            "address": {
                "city": "San Francisco",
                "county": "San Francisco County",
                "state": "California"
            }
        }

        with patch("src.services.geocoding.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_response
            mock_instance.get.return_value = mock_resp

            result = await reverse_geocode(37.7749, -122.4194)

            assert "San Francisco" in result

    @pytest.mark.asyncio
    async def test_reverse_geocode_success_with_village(self):
        """Test geocoding with village/town."""
        mock_response = {
            "address": {
                "village": "Half Moon Bay",
                "county": "San Mateo County"
            }
        }

        with patch("src.services.geocoding.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_response
            mock_instance.get.return_value = mock_resp

            result = await reverse_geocode(37.4636, -122.4286)

            assert "Half Moon Bay" in result

    @pytest.mark.asyncio
    async def test_reverse_geocode_fallback_to_display_name(self):
        """Test fallback to display_name when address is minimal."""
        mock_response = {
            "display_name": "123 Main St, San Francisco, CA, USA",
            "address": {}
        }

        with patch("src.services.geocoding.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_response
            mock_instance.get.return_value = mock_resp

            result = await reverse_geocode(37.7749, -122.4194)

            # Should take first 3 parts of display_name
            assert result is not None
            assert "San Francisco" in result or "Main St" in result

    @pytest.mark.asyncio
    async def test_reverse_geocode_empty_response(self):
        """Test handling of empty response."""
        with patch("src.services.geocoding.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {}
            mock_instance.get.return_value = mock_resp

            result = await reverse_geocode(0, 0)

            assert result is None

    @pytest.mark.asyncio
    async def test_reverse_geocode_non_200_status(self):
        """Test handling of non-200 HTTP status."""
        with patch("src.services.geocoding.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            mock_resp = MagicMock()
            mock_resp.status_code = 500
            mock_instance.get.return_value = mock_resp

            result = await reverse_geocode(37.7749, -122.4194)

            assert result is None

    @pytest.mark.asyncio
    async def test_reverse_geocode_timeout(self):
        """Test handling of timeout."""
        with patch("src.services.geocoding.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get.side_effect = httpx.TimeoutException("Timeout")

            result = await reverse_geocode(37.7749, -122.4194)

            assert result is None

    @pytest.mark.asyncio
    async def test_reverse_geocode_general_error(self):
        """Test handling of general errors."""
        with patch("src.services.geocoding.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get.side_effect = Exception("Connection error")

            result = await reverse_geocode(37.7749, -122.4194)

            assert result is None


class TestReverseGeocodeSync:
    """Tests for synchronous reverse geocoding."""

    def test_reverse_geocode_sync_with_poi(self):
        """Test sync geocoding with POI/amenity name."""
        mock_response = {
            "name": "Ferry Building",
            "address": {
                "amenity": "marketplace",
                "road": "The Embarcadero",
                "city": "San Francisco",
                "state": "California"
            }
        }

        with patch("src.services.geocoding.httpx.Client") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value.__enter__.return_value = mock_instance

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_response
            mock_instance.get.return_value = mock_resp

            result = reverse_geocode_sync(37.7955, -122.3937)

            assert "Ferry Building" in result

    def test_reverse_geocode_sync_with_street_address(self):
        """Test sync geocoding with street address."""
        mock_response = {
            "address": {
                "house_number": "123",
                "road": "Market Street",
                "city": "San Francisco",
                "state": "California"
            }
        }

        with patch("src.services.geocoding.httpx.Client") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value.__enter__.return_value = mock_instance

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_response
            mock_instance.get.return_value = mock_resp

            result = reverse_geocode_sync(37.7749, -122.4194)

            assert "123 Market Street" in result
            assert "San Francisco" in result

    def test_reverse_geocode_sync_with_road_only(self):
        """Test sync geocoding with road but no house number."""
        mock_response = {
            "address": {
                "road": "Highway 1",
                "city": "Pacifica",
                "state": "California"
            }
        }

        with patch("src.services.geocoding.httpx.Client") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value.__enter__.return_value = mock_instance

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_response
            mock_instance.get.return_value = mock_resp

            result = reverse_geocode_sync(37.6, -122.5)

            assert "Highway 1" in result

    def test_reverse_geocode_sync_with_neighborhood(self):
        """Test sync geocoding with neighborhood."""
        mock_response = {
            "address": {
                "neighbourhood": "Mission District",
                "city": "San Francisco",
                "state": "California"
            }
        }

        with patch("src.services.geocoding.httpx.Client") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value.__enter__.return_value = mock_instance

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_response
            mock_instance.get.return_value = mock_resp

            result = reverse_geocode_sync(37.7599, -122.4148)

            assert "Mission District" in result

    def test_reverse_geocode_sync_state_abbreviation(self):
        """Test that state names are abbreviated for US states."""
        mock_response = {
            "address": {
                "road": "Main Street",
                "city": "Portland",
                "state": "Oregon"
            }
        }

        with patch("src.services.geocoding.httpx.Client") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value.__enter__.return_value = mock_instance

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_response
            mock_instance.get.return_value = mock_resp

            result = reverse_geocode_sync(45.5152, -122.6784)

            # Oregon should be abbreviated to OR
            assert "OR" in result

    def test_reverse_geocode_sync_non_us_state(self):
        """Test that non-US states are not abbreviated."""
        mock_response = {
            "address": {
                "road": "Rue de Rivoli",
                "city": "Paris",
                "state": "Île-de-France"
            }
        }

        with patch("src.services.geocoding.httpx.Client") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value.__enter__.return_value = mock_instance

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_response
            mock_instance.get.return_value = mock_resp

            result = reverse_geocode_sync(48.8566, 2.3522)

            # Non-US state should be kept as-is
            assert "Île-de-France" in result

    def test_reverse_geocode_sync_fallback_to_display_name(self):
        """Test fallback to display_name."""
        mock_response = {
            "display_name": "Some Remote Location, Country",
            "address": {}
        }

        with patch("src.services.geocoding.httpx.Client") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value.__enter__.return_value = mock_instance

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_response
            mock_instance.get.return_value = mock_resp

            result = reverse_geocode_sync(0, 0)

            assert result is not None

    def test_reverse_geocode_sync_empty_response(self):
        """Test handling of empty response."""
        with patch("src.services.geocoding.httpx.Client") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value.__enter__.return_value = mock_instance

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {}
            mock_instance.get.return_value = mock_resp

            result = reverse_geocode_sync(0, 0)

            assert result is None

    def test_reverse_geocode_sync_non_200_status(self):
        """Test handling of non-200 status."""
        with patch("src.services.geocoding.httpx.Client") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value.__enter__.return_value = mock_instance

            mock_resp = MagicMock()
            mock_resp.status_code = 429  # Rate limit
            mock_instance.get.return_value = mock_resp

            result = reverse_geocode_sync(37.7749, -122.4194)

            assert result is None

    def test_reverse_geocode_sync_timeout(self):
        """Test handling of timeout."""
        with patch("src.services.geocoding.httpx.Client") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value.__enter__.return_value = mock_instance
            mock_instance.get.side_effect = httpx.TimeoutException("Timeout")

            result = reverse_geocode_sync(37.7749, -122.4194)

            assert result is None

    def test_reverse_geocode_sync_general_error(self):
        """Test handling of general errors."""
        with patch("src.services.geocoding.httpx.Client") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value.__enter__.return_value = mock_instance
            mock_instance.get.side_effect = Exception("Network error")

            result = reverse_geocode_sync(37.7749, -122.4194)

            assert result is None

    def test_reverse_geocode_sync_with_town(self):
        """Test geocoding with town instead of city."""
        mock_response = {
            "address": {
                "road": "Main Street",
                "town": "Sausalito",
                "state": "California"
            }
        }

        with patch("src.services.geocoding.httpx.Client") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value.__enter__.return_value = mock_instance

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_response
            mock_instance.get.return_value = mock_resp

            result = reverse_geocode_sync(37.8591, -122.4853)

            assert "Sausalito" in result

    def test_reverse_geocode_sync_pedestrian_path(self):
        """Test geocoding with pedestrian path."""
        mock_response = {
            "address": {
                "pedestrian": "Golden Gate Bridge",
                "city": "San Francisco",
                "state": "California"
            }
        }

        with patch("src.services.geocoding.httpx.Client") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value.__enter__.return_value = mock_instance

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_response
            mock_instance.get.return_value = mock_resp

            result = reverse_geocode_sync(37.8199, -122.4783)

            assert "Golden Gate Bridge" in result
