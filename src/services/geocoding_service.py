import requests
import time
from typing import Optional, Dict, Tuple
from sqlalchemy.orm import Session
from src.schemas.models import PlaceCoordinates
import logging

logger = logging.getLogger(__name__)

class GeocodingService:
    """Service for geocoding places using Nominatim API (OpenStreetMap)"""
    
    def __init__(self):
        self.base_url = "https://nominatim.openstreetmap.org/search"
        self.reverse_url = "https://nominatim.openstreetmap.org/reverse"
        self.headers = {
            'User-Agent': 'JOL-Travel-Bot/1.0 (travel-assistant)'
        }
        self.request_delay = 1  # Nominatim rate limit: 1 request per second
        self.last_request_time = 0
        
    def _rate_limit(self):
        """Ensure we don't exceed rate limits"""
        current_time = time.time()
        elapsed = current_time - self.last_request_time
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        self.last_request_time = time.time()
    
    def geocode_place(self, place_name: str, place_type: str = "general", 
                     city: str = "", country: str = "") -> Optional[Dict]:
        """
        Get coordinates for a place using Nominatim API
        
        Args:
            place_name: Name of the place (hotel name, restaurant name, etc.)
            place_type: Type of place (airport, hotel, restaurant, activity)
            city: City where the place is located
            country: Country where the place is located
            
        Returns:
            Dict with coordinates and address info or None if not found
        """
        try:
            self._rate_limit()
            
            # Build search query
            query_parts = [place_name]
            if city:
                query_parts.append(city)
            if country:
                query_parts.append(country)
            
            query = ", ".join(query_parts)
            
            # Determine appropriate search category
            category_map = {
                "airport": "aeroway",
                "hotel": "tourism",
                "restaurant": "amenity", 
                "activity": "tourism"
            }
            
            params = {
                'q': query,
                'format': 'json',
                'limit': 5,
                'addressdetails': 1,
                'extratags': 1
            }
            
            # Add category filter if available
            if place_type in category_map:
                if place_type == "airport":
                    params['amenity'] = 'airport'
                elif place_type == "hotel":
                    params['amenity'] = 'hotel,guest_house,hostel'
                elif place_type == "restaurant":
                    params['amenity'] = 'restaurant,cafe,fast_food'
                elif place_type == "activity":
                    params['tourism'] = 'attraction,museum,zoo,aquarium'
            
            response = requests.get(self.base_url, params=params, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            results = response.json()
            
            if not results:
                logger.warning(f"No geocoding results found for: {query}")
                return None
            
            # Get the best result (first one is usually most relevant)
            best_result = results[0]
            
            return {
                'latitude': float(best_result['lat']),
                'longitude': float(best_result['lon']),
                'display_name': best_result.get('display_name', ''),
                'address': self._parse_address(best_result.get('address', {})),
                'country': best_result.get('address', {}).get('country', ''),
                'city': self._extract_city(best_result.get('address', {})),
                'place_id': best_result.get('place_id'),
                'osm_type': best_result.get('osm_type'),
                'osm_id': best_result.get('osm_id')
            }
            
        except requests.RequestException as e:
            logger.error(f"Geocoding request failed for {place_name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Geocoding error for {place_name}: {e}")
            return None
    
    def _parse_address(self, address_data: Dict) -> str:
        """Parse address components into a readable string"""
        components = []
        
        # Priority order for address components
        priority_keys = ['house_number', 'road', 'neighbourhood', 'suburb', 
                        'city', 'town', 'village', 'state', 'country']
        
        for key in priority_keys:
            if key in address_data and address_data[key]:
                components.append(address_data[key])
        
        return ", ".join(components) if components else ""
    
    def _extract_city(self, address_data: Dict) -> str:
        """Extract city name from address data"""
        city_keys = ['city', 'town', 'village', 'municipality']
        for key in city_keys:
            if key in address_data and address_data[key]:
                return address_data[key]
        return ""
    
    def geocode_airport(self, airport_code: str, airport_name: str = "") -> Optional[Dict]:
        """
        Geocode airport using IATA/ICAO code and name
        
        Args:
            airport_code: IATA or ICAO airport code (e.g., 'ALA', 'JFK')
            airport_name: Full airport name (optional)
            
        Returns:
            Dict with coordinates and info or None
        """
        try:
            # Try with airport code first
            search_terms = [
                f"{airport_code} airport",
                f"{airport_name} airport" if airport_name else "",
                f"IATA {airport_code}",
                f"airport {airport_code}"
            ]
            
            for search_term in search_terms:
                if not search_term:
                    continue
                    
                result = self.geocode_place(search_term, "airport")
                if result:
                    return result
            
            return None
            
        except Exception as e:
            logger.error(f"Airport geocoding error for {airport_code}: {e}")
            return None
    
    def reverse_geocode(self, latitude: float, longitude: float) -> Optional[Dict]:
        """
        Get address information from coordinates
        
        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            
        Returns:
            Dict with address info or None
        """
        try:
            self._rate_limit()
            
            params = {
                'lat': latitude,
                'lon': longitude,
                'format': 'json',
                'addressdetails': 1
            }
            
            response = requests.get(self.reverse_url, params=params, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            
            if 'error' in result:
                return None
            
            return {
                'display_name': result.get('display_name', ''),
                'address': self._parse_address(result.get('address', {})),
                'country': result.get('address', {}).get('country', ''),
                'city': self._extract_city(result.get('address', {}))
            }
            
        except Exception as e:
            logger.error(f"Reverse geocoding error for {latitude}, {longitude}: {e}")
            return None
    
    def get_or_create_coordinates(self, db: Session, place_name: str, place_type: str, 
                                city: str = "", country: str = "") -> Optional[PlaceCoordinates]:
        """
        Get coordinates from database or create new entry by geocoding
        
        Args:
            db: Database session
            place_name: Name of the place
            place_type: Type of place (airport, hotel, restaurant, activity)
            city: City name (optional)
            country: Country name (optional)
            
        Returns:
            PlaceCoordinates object or None if geocoding fails
        """
        try:
            # First, try to find existing coordinates
            existing = db.query(PlaceCoordinates).filter(
                PlaceCoordinates.place_name.ilike(f"%{place_name}%"),
                PlaceCoordinates.place_type == place_type
            ).first()
            
            if existing:
                logger.info(f"Found existing coordinates for {place_name}")
                return existing
            
            # If not found, geocode the place
            logger.info(f"Geocoding new place: {place_name}")
            geocoding_result = self.geocode_place(place_name, place_type, city, country)
            
            if not geocoding_result:
                logger.warning(f"Could not geocode {place_name}")
                return None
            
            # Create new PlaceCoordinates entry
            place_coordinates = PlaceCoordinates(
                place_name=place_name,
                place_type=place_type,
                latitude=geocoding_result['latitude'],
                longitude=geocoding_result['longitude'],
                address=geocoding_result['address'],
                country=geocoding_result['country'],
                city=geocoding_result['city']
            )
            
            db.add(place_coordinates)
            db.commit()
            db.refresh(place_coordinates)
            
            logger.info(f"Created coordinates for {place_name}: "
                       f"{geocoding_result['latitude']}, {geocoding_result['longitude']}")
            
            return place_coordinates
            
        except Exception as e:
            logger.error(f"Error getting/creating coordinates for {place_name}: {e}")
            db.rollback()
            return None

# Global geocoding service instance
geocoding_service = GeocodingService() 