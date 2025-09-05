from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime, date, timedelta
from src.schemas.models import (
    TravelRoadmap, RoadmapItem, BookingInDB, PlaceCoordinates,
    TravelRoadmapSchema, RoadmapItemSchema, UserInDB
)
from src.services.geocoding_service import geocoding_service
from ai.roadmap_planner_agent import roadmap_planner_agent
import json
import logging

logger = logging.getLogger(__name__)

class RoadmapService:
    """Service for managing travel roadmaps and automatically organizing bookings"""
    
    def __init__(self):
        pass
    
    def create_or_update_roadmap_from_booking(self, db: Session, user: UserInDB, 
                                            booking: BookingInDB) -> Optional[TravelRoadmap]:
        """
        Create or update roadmap when user makes a booking
        
        Args:
            db: Database session
            user: User who made the booking
            booking: The booking that was just created
            
        Returns:
            Updated/created TravelRoadmap or None
        """
        try:
            booking_data = json.loads(booking.data) if isinstance(booking.data, str) else booking.data
            
            # Extract travel dates and destination from booking
            travel_info = self._extract_travel_info(booking, booking_data)
            
            if not travel_info:
                logger.warning(f"Could not extract travel info from booking {booking.id}")
                return None
            
            # Find or create appropriate roadmap
            roadmap = self._find_or_create_roadmap(
                db, user, travel_info['destination'], 
                travel_info['start_date'], travel_info['end_date']
            )
            
            if not roadmap:
                logger.error("Failed to create/find roadmap")
                return None
            
            # Get coordinates for the place
            coordinates = self._get_place_coordinates(db, booking, booking_data)
            
            # Create roadmap item
            roadmap_item = self._create_roadmap_item(
                db, roadmap, booking, booking_data, coordinates, travel_info
            )
            
            if roadmap_item:
                # Reorder roadmap items by date/time
                self._reorder_roadmap_items(db, roadmap)
                
                # Update roadmap dates
                self._update_roadmap_dates(db, roadmap)
                
                # Generate AI roadmap if enough bookings accumulated
                self._try_generate_ai_roadmap(db, roadmap, user)
                
                logger.info(f"Added booking {booking.id} to roadmap {roadmap.id}")
                return roadmap
            
            return None
            
        except Exception as e:
            logger.error(f"Error creating/updating roadmap from booking: {e}")
            return None
    
    async def generate_ai_roadmap(self, db: Session, roadmap_id: int, user: UserInDB, 
                                user_preferences: Dict = None, regenerate: bool = False) -> TravelRoadmap:
        """
        Generate AI-powered detailed roadmap with daily itineraries
        
        Args:
            db: Database session
            roadmap_id: ID of roadmap to generate AI content for
            user: User who owns the roadmap
            user_preferences: User preferences for roadmap generation
            regenerate: Whether to regenerate existing AI roadmap
            
        Returns:
            Updated roadmap with AI-generated content
        """
        try:
            roadmap = db.query(TravelRoadmap).filter(
                TravelRoadmap.id == roadmap_id,
                TravelRoadmap.user_id == user.id
            ).first()
            
            if not roadmap:
                raise ValueError("Roadmap not found")
            
            # Check if AI roadmap already exists and regenerate is False
            if roadmap.ai_generated and not regenerate:
                logger.info(f"AI roadmap already exists for roadmap {roadmap_id}")
                return roadmap
            
            # Get all bookings for this roadmap
            bookings_data = self._get_roadmap_bookings_data(db, roadmap)
            
            if not bookings_data:
                logger.warning(f"No bookings found for roadmap {roadmap_id}")
                return roadmap
            
            # Generate AI roadmap
            logger.info(f"Generating AI roadmap for roadmap {roadmap_id}")
            ai_roadmap = await roadmap_planner_agent.generate_roadmap(
                bookings_data, user_preferences
            )
            
            if "error" in ai_roadmap:
                logger.error(f"AI roadmap generation failed: {ai_roadmap['error']}")
                return roadmap
            
            # Update roadmap with AI-generated content
            roadmap.ai_generated = True
            roadmap.roadmap_summary = json.dumps(ai_roadmap.get('roadmap_summary', {}), ensure_ascii=False)
            roadmap.daily_itinerary = json.dumps(ai_roadmap.get('daily_itinerary', []), ensure_ascii=False)
            roadmap.general_tips = json.dumps(ai_roadmap.get('general_tips', {}), ensure_ascii=False)
            roadmap.alternative_options = json.dumps(ai_roadmap.get('alternative_options', {}), ensure_ascii=False)
            
            if user_preferences:
                roadmap.user_preferences = json.dumps(user_preferences, ensure_ascii=False)
            
            # Update title and description from AI if provided
            summary = ai_roadmap.get('roadmap_summary', {})
            if summary.get('title'):
                roadmap.title = summary['title']
            if summary.get('description'):
                roadmap.description = summary['description']
            
            db.commit()
            db.refresh(roadmap)
            
            logger.info(f"Successfully generated AI roadmap for roadmap {roadmap_id}")
            return roadmap
            
        except Exception as e:
            logger.error(f"Error generating AI roadmap: {e}")
            db.rollback()
            raise e
    
    async def enhance_roadmap(self, db: Session, roadmap_id: int, user: UserInDB, 
                            additional_context: str = "") -> TravelRoadmap:
        """
        Enhance existing AI roadmap with additional context
        
        Args:
            db: Database session
            roadmap_id: ID of roadmap to enhance
            user: User who owns the roadmap
            additional_context: Additional information for enhancement
            
        Returns:
            Enhanced roadmap
        """
        try:
            roadmap = db.query(TravelRoadmap).filter(
                TravelRoadmap.id == roadmap_id,
                TravelRoadmap.user_id == user.id
            ).first()
            
            if not roadmap or not roadmap.ai_generated:
                raise ValueError("AI roadmap not found")
            
            # Get current AI roadmap data
            current_roadmap = {
                'roadmap_summary': json.loads(roadmap.roadmap_summary) if roadmap.roadmap_summary else {},
                'daily_itinerary': json.loads(roadmap.daily_itinerary) if roadmap.daily_itinerary else [],
                'general_tips': json.loads(roadmap.general_tips) if roadmap.general_tips else {},
                'alternative_options': json.loads(roadmap.alternative_options) if roadmap.alternative_options else {}
            }
            
            # Enhance roadmap using AI
            enhanced_roadmap = await roadmap_planner_agent.enhance_existing_roadmap(
                current_roadmap, additional_context
            )
            
            # Update roadmap with enhanced content
            roadmap.roadmap_summary = json.dumps(enhanced_roadmap.get('roadmap_summary', {}), ensure_ascii=False)
            roadmap.daily_itinerary = json.dumps(enhanced_roadmap.get('daily_itinerary', []), ensure_ascii=False)
            roadmap.general_tips = json.dumps(enhanced_roadmap.get('general_tips', {}), ensure_ascii=False)
            roadmap.alternative_options = json.dumps(enhanced_roadmap.get('alternative_options', {}), ensure_ascii=False)
            
            db.commit()
            db.refresh(roadmap)
            
            logger.info(f"Successfully enhanced roadmap {roadmap_id}")
            return roadmap
            
        except Exception as e:
            logger.error(f"Error enhancing roadmap: {e}")
            db.rollback()
            raise e
    
    def _try_generate_ai_roadmap(self, db: Session, roadmap: TravelRoadmap, user: UserInDB):
        """
        Try to generate AI roadmap if conditions are met (automatic trigger)
        
        Args:
            db: Database session
            roadmap: Roadmap to potentially generate AI content for
            user: User who owns the roadmap
        """
        try:
            # Check if AI roadmap already exists
            if roadmap.ai_generated:
                logger.info(f"AI roadmap already exists for roadmap {roadmap.id}")
                return
            
            # Get all roadmap items for analysis
            roadmap_items = db.query(RoadmapItem).filter(
                RoadmapItem.roadmap_id == roadmap.id
            ).all()
            
            # Analyze booking types and readiness
            booking_types = set()
            has_transport = False
            has_accommodation = False
            has_dates = bool(roadmap.start_date and roadmap.end_date)
            
            for item in roadmap_items:
                booking_types.add(item.item_type)
                if item.item_type == "ticket":
                    has_transport = True
                elif item.item_type == "hotel":
                    has_accommodation = True
            
            booking_count = len(roadmap_items)
            
            # Smart criteria for AI roadmap generation
            is_ready_for_ai = (
                booking_count >= 2 and  # At least 2 bookings
                has_transport and       # Must have flights
                has_accommodation and   # Must have hotel
                has_dates              # Must have travel dates
            )
            
            if is_ready_for_ai:
                logger.info(f"Roadmap {roadmap.id} meets criteria for AI generation. Triggering automatic generation...")
                
                # Mark roadmap as pending AI generation
                roadmap.description = (roadmap.description or "") + " [AI generation pending]"
                
                # Import asyncio for running async function
                import asyncio
                
                # Create event loop if none exists (for sync context)
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # If we're in an async context, schedule the task
                        asyncio.create_task(self._generate_ai_roadmap_async(db, roadmap, user))
                    else:
                        # If we're in a sync context, run the async function
                        loop.run_until_complete(self._generate_ai_roadmap_async(db, roadmap, user))
                except RuntimeError:
                    # No event loop, create a new one
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(self._generate_ai_roadmap_async(db, roadmap, user))
                    finally:
                        loop.close()
                        
                logger.info(f"AI roadmap generation completed for roadmap {roadmap.id}")
            else:
                logger.info(f"Roadmap {roadmap.id} not ready for AI generation yet. "
                          f"Has {booking_count} bookings, transport: {has_transport}, "
                          f"accommodation: {has_accommodation}, dates: {has_dates}")
                
        except Exception as e:
            logger.error(f"Error in AI roadmap trigger: {e}")
    
    async def _generate_ai_roadmap_async(self, db: Session, roadmap: TravelRoadmap, user: UserInDB):
        """
        Async helper to generate AI roadmap automatically
        """
        try:
            # Get bookings data for this roadmap
            bookings_data = self._get_roadmap_bookings_data(db, roadmap)
            
            if not bookings_data:
                logger.warning(f"No bookings found for automatic AI generation of roadmap {roadmap.id}")
                return
            
            logger.info(f"Automatically generating AI roadmap for roadmap {roadmap.id}")
            
            # Generate AI roadmap with default preferences
            default_preferences = {
                "interests": ["culture", "food", "sightseeing"],
                "budget": "moderate",
                "pace": "relaxed",
                "group_type": "travelers"
            }
            
            ai_roadmap = await roadmap_planner_agent.generate_roadmap(
                bookings_data, default_preferences
            )
            
            if "error" in ai_roadmap:
                logger.error(f"Automatic AI roadmap generation failed: {ai_roadmap['error']}")
                # Remove pending marker
                if "[AI generation pending]" in roadmap.description:
                    roadmap.description = roadmap.description.replace(" [AI generation pending]", "")
                    db.commit()
                return
            
            # Update roadmap with AI-generated content
            roadmap.ai_generated = True
            roadmap.roadmap_summary = json.dumps(ai_roadmap.get('roadmap_summary', {}), ensure_ascii=False)
            roadmap.daily_itinerary = json.dumps(ai_roadmap.get('daily_itinerary', []), ensure_ascii=False)
            roadmap.general_tips = json.dumps(ai_roadmap.get('general_tips', {}), ensure_ascii=False)
            roadmap.alternative_options = json.dumps(ai_roadmap.get('alternative_options', {}), ensure_ascii=False)
            roadmap.user_preferences = json.dumps(default_preferences, ensure_ascii=False)
            
            # Update title and description from AI if provided
            summary = ai_roadmap.get('roadmap_summary', {})
            if summary.get('title'):
                roadmap.title = summary['title']
            if summary.get('description'):
                roadmap.description = summary['description']
            
            # Remove pending marker if it exists
            if "[AI generation pending]" in (roadmap.description or ""):
                roadmap.description = roadmap.description.replace(" [AI generation pending]", "")
            
            db.commit()
            db.refresh(roadmap)
            
            logger.info(f"Successfully auto-generated AI roadmap for roadmap {roadmap.id}")
            
        except Exception as e:
            logger.error(f"Error in automatic AI roadmap generation: {e}")
            # Remove pending marker on error
            try:
                if "[AI generation pending]" in (roadmap.description or ""):
                    roadmap.description = roadmap.description.replace(" [AI generation pending]", "")
                    db.commit()
            except:
                pass
    
    def _get_roadmap_bookings_data(self, db: Session, roadmap: TravelRoadmap) -> List[Dict]:
        """Get all booking data for a roadmap"""
        try:
            roadmap_items = db.query(RoadmapItem).filter(
                RoadmapItem.roadmap_id == roadmap.id
            ).order_by(RoadmapItem.order_index.asc()).all()
            
            bookings_data = []
            for item in roadmap_items:
                if item.booking_id:
                    # Get booking data
                    booking = db.query(BookingInDB).filter(
                        BookingInDB.id == item.booking_id
                    ).first()
                    
                    if booking:
                        booking_data = {
                            'booking_type': booking.booking_type,
                            'item_type': item.item_type,
                            'data': json.loads(booking.data) if isinstance(booking.data, str) else booking.data,
                            'start_datetime': item.start_datetime,
                            'end_datetime': item.end_datetime,
                            'coordinates': None
                        }
                        
                        # Add coordinates if available
                        if item.place_coordinates_id:
                            coordinates = db.query(PlaceCoordinates).filter(
                                PlaceCoordinates.id == item.place_coordinates_id
                            ).first()
                            if coordinates:
                                booking_data['coordinates'] = {
                                    'latitude': coordinates.latitude,
                                    'longitude': coordinates.longitude,
                                    'place_name': coordinates.place_name,
                                    'city': coordinates.city,
                                    'country': coordinates.country
                                }
                        
                        bookings_data.append(booking_data)
            
            return bookings_data
            
        except Exception as e:
            logger.error(f"Error getting roadmap bookings data: {e}")
            return []
    
    def _extract_travel_info(self, booking: BookingInDB, booking_data: Dict) -> Optional[Dict]:
        """Extract travel information from booking data"""
        try:
            travel_info = {
                'destination': '',
                'start_date': None,
                'end_date': None,
                'start_datetime': None,
                'end_datetime': None
            }
            
            if booking.booking_type == "ticket":
                # Extract from flight data
                flights_to = booking_data.get('flights_to', [])
                flights_return = booking_data.get('flights_return', [])
                
                if flights_to:
                    first_flight = flights_to[0]
                    travel_info['destination'] = first_flight.get('to', '')
                    
                    # Parse departure date/time
                    dep_date = first_flight.get('departure_date')
                    dep_time = first_flight.get('departure_time')
                    if dep_date:
                        travel_info['start_date'] = datetime.strptime(dep_date, '%Y-%m-%d').date()
                        if dep_time:
                            travel_info['start_datetime'] = datetime.strptime(
                                f"{dep_date} {dep_time}", '%Y-%m-%d %H:%M'
                            )
                
                if flights_return:
                    last_flight = flights_return[-1]
                    arr_date = last_flight.get('arrival_date')
                    arr_time = last_flight.get('arrival_time')
                    if arr_date:
                        travel_info['end_date'] = datetime.strptime(arr_date, '%Y-%m-%d').date()
                        if arr_time:
                            travel_info['end_datetime'] = datetime.strptime(
                                f"{arr_date} {arr_time}", '%Y-%m-%d %H:%M'
                            )
            
            elif booking.booking_type == "hotel":
                # Extract from hotel data
                travel_info['destination'] = booking_data.get('city', booking_data.get('location', ''))
                
                # Try to parse check-in/check-out dates
                check_in = booking_data.get('check_in_date', booking_data.get('checkin_date'))
                check_out = booking_data.get('check_out_date', booking_data.get('checkout_date'))
                
                if check_in:
                    if isinstance(check_in, str):
                        travel_info['start_date'] = datetime.strptime(check_in, '%Y-%m-%d').date()
                        travel_info['start_datetime'] = datetime.strptime(check_in + ' 15:00', '%Y-%m-%d %H:%M')
                
                if check_out:
                    if isinstance(check_out, str):
                        travel_info['end_date'] = datetime.strptime(check_out, '%Y-%m-%d').date()
                        travel_info['end_datetime'] = datetime.strptime(check_out + ' 11:00', '%Y-%m-%d %H:%M')
            
            elif booking.booking_type in ["restaurant", "activity"]:
                # Extract location info
                travel_info['destination'] = booking_data.get('city', booking_data.get('location', ''))
                
                # For restaurants and activities, set start time to current day if not specified
                if not travel_info['start_date']:
                    travel_info['start_date'] = date.today()
                    travel_info['start_datetime'] = datetime.now()
            
            return travel_info if travel_info['destination'] else None
            
        except Exception as e:
            logger.error(f"Error extracting travel info: {e}")
            return None
    
    def _find_or_create_roadmap(self, db: Session, user: UserInDB, destination: str, 
                              start_date: Optional[date], end_date: Optional[date]) -> Optional[TravelRoadmap]:
        """Find existing roadmap or create a new one"""
        try:
            # Look for existing active roadmap with similar destination and dates
            query = db.query(TravelRoadmap).filter(
                TravelRoadmap.user_id == user.id,
                TravelRoadmap.is_active == True
            )
            
            # If we have dates, look for overlapping roadmaps
            if start_date:
                query = query.filter(
                    (TravelRoadmap.start_date.is_(None)) |
                    (TravelRoadmap.end_date.is_(None)) |
                    (TravelRoadmap.start_date <= start_date + timedelta(days=7)) |
                    (TravelRoadmap.end_date >= start_date - timedelta(days=7))
                )
            
            existing_roadmaps = query.all()
            
            # Check if any existing roadmap matches the destination
            for roadmap in existing_roadmaps:
                if (destination.lower() in roadmap.title.lower() or 
                    destination.lower() in (roadmap.description or "").lower()):
                    logger.info(f"Found existing roadmap {roadmap.id} for destination {destination}")
                    return roadmap
            
            # Create new roadmap
            title = self._generate_roadmap_title(destination, start_date, end_date)
            description = f"Travel to {destination}"
            
            if start_date and end_date:
                description += f" from {start_date} to {end_date}"
            elif start_date:
                description += f" starting {start_date}"
            
            new_roadmap = TravelRoadmap(
                user_id=user.id,
                title=title,
                description=description,
                start_date=start_date,
                end_date=end_date
            )
            
            db.add(new_roadmap)
            db.commit()
            db.refresh(new_roadmap)
            
            logger.info(f"Created new roadmap {new_roadmap.id}: {title}")
            return new_roadmap
            
        except Exception as e:
            logger.error(f"Error finding/creating roadmap: {e}")
            db.rollback()
            return None
    
    def _generate_roadmap_title(self, destination: str, start_date: Optional[date], 
                              end_date: Optional[date]) -> str:
        """Generate a descriptive title for the roadmap"""
        title = f"Trip to {destination}"
        
        if start_date:
            if end_date and start_date != end_date:
                title += f" ({start_date.strftime('%b %d')} - {end_date.strftime('%b %d')})"
            else:
                title += f" ({start_date.strftime('%b %d, %Y')})"
        
        return title
    
    def _get_place_coordinates(self, db: Session, booking: BookingInDB, 
                             booking_data: Dict) -> Optional[PlaceCoordinates]:
        """Get or create coordinates for the booked place"""
        try:
            place_name = ""
            place_type = booking.booking_type
            city = ""
            country = ""
            
            if booking.booking_type == "ticket":
                # For flights, get destination airport
                flights_to = booking_data.get('flights_to', [])
                if flights_to:
                    place_name = flights_to[-1].get('to', '')  # Final destination
                    place_type = "airport"
                    
            elif booking.booking_type == "hotel":
                place_name = booking_data.get('name', booking_data.get('hotel_name', ''))
                city = booking_data.get('city', booking_data.get('location', ''))
                country = booking_data.get('country', '')
                
            elif booking.booking_type == "restaurant":
                place_name = booking_data.get('name', booking_data.get('restaurant_name', ''))
                city = booking_data.get('city', booking_data.get('location', ''))
                country = booking_data.get('country', '')
                
            elif booking.booking_type == "activity":
                place_name = booking_data.get('name', booking_data.get('title', ''))
                city = booking_data.get('city', booking_data.get('location', ''))
                country = booking_data.get('country', '')
            
            if not place_name:
                logger.warning(f"No place name found for booking {booking.id}")
                return None
            
            # Get or create coordinates
            coordinates = geocoding_service.get_or_create_coordinates(
                db, place_name, place_type, city, country
            )
            
            return coordinates
            
        except Exception as e:
            logger.error(f"Error getting place coordinates: {e}")
            return None
    
    def _create_roadmap_item(self, db: Session, roadmap: TravelRoadmap, booking: BookingInDB,
                           booking_data: Dict, coordinates: Optional[PlaceCoordinates],
                           travel_info: Dict) -> Optional[RoadmapItem]:
        """Create a roadmap item from booking"""
        try:
            title = self._generate_item_title(booking, booking_data)
            description = self._generate_item_description(booking, booking_data)
            
            roadmap_item = RoadmapItem(
                roadmap_id=roadmap.id,
                booking_id=booking.id,
                place_coordinates_id=coordinates.id if coordinates else None,
                item_type=booking.booking_type,
                title=title,
                description=description,
                start_datetime=travel_info.get('start_datetime'),
                end_datetime=travel_info.get('end_datetime'),
                order_index=0,  # Will be updated by reordering
                data=json.dumps(booking_data, ensure_ascii=False)
            )
            
            db.add(roadmap_item)
            db.commit()
            db.refresh(roadmap_item)
            
            logger.info(f"Created roadmap item {roadmap_item.id}: {title}")
            return roadmap_item
            
        except Exception as e:
            logger.error(f"Error creating roadmap item: {e}")
            db.rollback()
            return None
    
    def _generate_item_title(self, booking: BookingInDB, booking_data: Dict) -> str:
        """Generate title for roadmap item"""
        if booking.booking_type == "ticket":
            flights_to = booking_data.get('flights_to', [])
            if flights_to:
                first_flight = flights_to[0]
                return f"Flight from {first_flight.get('from', '')} to {first_flight.get('to', '')}"
            return "Flight"
            
        elif booking.booking_type == "hotel":
            hotel_name = booking_data.get('name', booking_data.get('hotel_name', 'Hotel'))
            return f"Stay at {hotel_name}"
            
        elif booking.booking_type == "restaurant":
            restaurant_name = booking_data.get('name', booking_data.get('restaurant_name', 'Restaurant'))
            return f"Dine at {restaurant_name}"
            
        elif booking.booking_type == "activity":
            activity_name = booking_data.get('name', booking_data.get('title', 'Activity'))
            return f"Visit {activity_name}"
        
        return f"{booking.booking_type.title()} Booking"
    
    def _generate_item_description(self, booking: BookingInDB, booking_data: Dict) -> str:
        """Generate description for roadmap item"""
        descriptions = []
        
        if booking.booking_type == "ticket":
            price = booking_data.get('price', '')
            currency = booking_data.get('currency', '')
            if price and currency:
                descriptions.append(f"Price: {price} {currency}")
                
            flights_to = booking_data.get('flights_to', [])
            if flights_to:
                for flight in flights_to:
                    airline = flight.get('airline', '')
                    flight_number = flight.get('flight_number', '')
                    if airline and flight_number:
                        descriptions.append(f"{airline} {flight_number}")
                        
        elif booking.booking_type == "hotel":
            price = booking_data.get('search_price_value', booking_data.get('price', ''))
            currency = booking_data.get('search_price_currency', booking_data.get('currency', ''))
            if price and currency:
                descriptions.append(f"Price: {price} {currency}")
                
            rating = booking_data.get('search_rating', booking_data.get('rating', ''))
            if rating:
                descriptions.append(f"Rating: {rating}")
                
        elif booking.booking_type in ["restaurant", "activity"]:
            rating = booking_data.get('rating', '')
            if rating:
                descriptions.append(f"Rating: {rating}")
                
            price_level = booking_data.get('price_level', '')
            if price_level:
                descriptions.append(f"Price level: {price_level}")
        
        return " | ".join(descriptions) if descriptions else ""
    
    def _reorder_roadmap_items(self, db: Session, roadmap: TravelRoadmap):
        """Reorder roadmap items by start datetime"""
        try:
            items = db.query(RoadmapItem).filter(
                RoadmapItem.roadmap_id == roadmap.id
            ).order_by(RoadmapItem.start_datetime.asc().nullslast()).all()
            
            for index, item in enumerate(items):
                item.order_index = index
            
            db.commit()
            logger.info(f"Reordered {len(items)} items in roadmap {roadmap.id}")
            
        except Exception as e:
            logger.error(f"Error reordering roadmap items: {e}")
            db.rollback()
    
    def _update_roadmap_dates(self, db: Session, roadmap: TravelRoadmap):
        """Update roadmap start and end dates based on items"""
        try:
            items = db.query(RoadmapItem).filter(
                RoadmapItem.roadmap_id == roadmap.id,
                RoadmapItem.start_datetime.isnot(None)
            ).order_by(RoadmapItem.start_datetime.asc()).all()
            
            if items:
                earliest_item = items[0]
                latest_item = items[-1]
                
                # Update start date if not set or if we found an earlier date
                if earliest_item.start_datetime:
                    new_start_date = earliest_item.start_datetime.date()
                    if not roadmap.start_date or new_start_date < roadmap.start_date:
                        roadmap.start_date = new_start_date
                
                # Update end date if not set or if we found a later date
                if latest_item.end_datetime:
                    new_end_date = latest_item.end_datetime.date()
                elif latest_item.start_datetime:
                    new_end_date = latest_item.start_datetime.date()
                else:
                    new_end_date = None
                    
                if new_end_date and (not roadmap.end_date or new_end_date > roadmap.end_date):
                    roadmap.end_date = new_end_date
                
                db.commit()
                logger.info(f"Updated roadmap {roadmap.id} dates: {roadmap.start_date} to {roadmap.end_date}")
                
        except Exception as e:
            logger.error(f"Error updating roadmap dates: {e}")
            db.rollback()
    
    def get_user_roadmaps(self, db: Session, user: UserInDB, active_only: bool = True) -> List[TravelRoadmap]:
        """Get all roadmaps for a user"""
        query = db.query(TravelRoadmap).filter(TravelRoadmap.user_id == user.id)
        
        if active_only:
            query = query.filter(TravelRoadmap.is_active == True)
        
        return query.order_by(TravelRoadmap.created_at.desc()).all()
    
    def get_roadmap_with_items(self, db: Session, roadmap_id: int, user: UserInDB) -> Optional[TravelRoadmap]:
        """Get roadmap with all its items for the user"""
        try:
            roadmap = db.query(TravelRoadmap).filter(
                TravelRoadmap.id == roadmap_id,
                TravelRoadmap.user_id == user.id
            ).first()
            return roadmap
        except Exception as e:
            logger.error(f"Error getting roadmap with items: {e}")
            return None

    def check_for_new_ai_roadmaps(self, db: Session, user: UserInDB) -> List[TravelRoadmap]:
        """
        Check for newly generated AI roadmaps for the user
        Returns roadmaps that were recently auto-generated and not yet viewed
        
        Args:
            db: Database session
            user: User to check roadmaps for
            
        Returns:
            List of newly generated AI roadmaps
        """
        try:
            # Find AI-generated roadmaps created in the last hour that haven't been "seen"
            from datetime import datetime, timedelta
            recent_time = datetime.now() - timedelta(hours=1)
            
            new_ai_roadmaps = db.query(TravelRoadmap).filter(
                TravelRoadmap.user_id == user.id,
                TravelRoadmap.ai_generated == True,
                TravelRoadmap.updated_at >= recent_time,
                TravelRoadmap.is_active == True,
                # Check if description doesn't contain "viewed" marker
                ~TravelRoadmap.description.contains("[viewed]")
            ).all()
            
            return new_ai_roadmaps
            
        except Exception as e:
            logger.error(f"Error checking for new AI roadmaps: {e}")
            return []
    
    def mark_roadmap_as_viewed(self, db: Session, roadmap_id: int, user: UserInDB) -> bool:
        """
        Mark roadmap as viewed by adding marker to description
        
        Args:
            db: Database session
            roadmap_id: ID of roadmap to mark as viewed
            user: User who viewed the roadmap
            
        Returns:
            True if successfully marked, False otherwise
        """
        try:
            roadmap = db.query(TravelRoadmap).filter(
                TravelRoadmap.id == roadmap_id,
                TravelRoadmap.user_id == user.id
            ).first()
            
            if roadmap and "[viewed]" not in (roadmap.description or ""):
                roadmap.description = (roadmap.description or "") + " [viewed]"
                db.commit()
                return True
            return False
            
        except Exception as e:
            logger.error(f"Error marking roadmap as viewed: {e}")
            return False

# Global roadmap service instance
roadmap_service = RoadmapService() 