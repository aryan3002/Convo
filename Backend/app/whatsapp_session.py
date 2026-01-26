"""
Simple in-memory session management for WhatsApp conversations.

Stores temporary conversation state for cancel flow and other multi-step interactions.
In production, consider using Redis or database for persistence.
"""

from datetime import datetime, timedelta
from typing import Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)

# In-memory session store: {phone_number: {data}}
# Each session has: state, data, expires_at
_sessions: Dict[str, Dict[str, Any]] = {}

# Session expiration time (15 minutes)
SESSION_TIMEOUT = timedelta(minutes=15)


def _cleanup_expired_sessions():
    """Remove expired sessions."""
    now = datetime.now()
    expired = [phone for phone, session in _sessions.items() if session.get('expires_at', now) < now]
    for phone in expired:
        del _sessions[phone]
        logger.debug(f"Cleaned up expired session for {phone}")


def set_session(phone: str, state: str, data: Optional[Dict] = None):
    """
    Set session state for a customer.
    
    Args:
        phone: Customer phone number
        state: Session state (e.g., 'awaiting_cancel_selection')
        data: Optional session data
    """
    _cleanup_expired_sessions()
    
    _sessions[phone] = {
        'state': state,
        'data': data or {},
        'expires_at': datetime.now() + SESSION_TIMEOUT,
    }
    logger.debug(f"Session set for {phone}: state={state}")


def get_session(phone: str) -> Optional[Dict[str, Any]]:
    """
    Get session for a customer.
    
    Args:
        phone: Customer phone number
        
    Returns:
        Session dictionary or None if not found/expired
    """
    _cleanup_expired_sessions()
    
    session = _sessions.get(phone)
    if session:
        # Check if expired
        if session.get('expires_at', datetime.now()) < datetime.now():
            del _sessions[phone]
            return None
    
    return session


def clear_session(phone: str):
    """
    Clear session for a customer.
    
    Args:
        phone: Customer phone number
    """
    if phone in _sessions:
        del _sessions[phone]
        logger.debug(f"Session cleared for {phone}")


def update_session_data(phone: str, data: Dict):
    """
    Update session data without changing state.
    
    Args:
        phone: Customer phone number
        data: Data to merge into session
    """
    session = get_session(phone)
    if session:
        session['data'].update(data)
        session['expires_at'] = datetime.now() + SESSION_TIMEOUT
        _sessions[phone] = session
        logger.debug(f"Session data updated for {phone}")
