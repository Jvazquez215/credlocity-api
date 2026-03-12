"""
Credlocity Google Voice Integration Service
Handles calls and SMS via Google Voice
"""
import os
import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Google Voice credentials from environment
GOOGLE_VOICE_EMAIL = os.environ.get("GOOGLE_VOICE_EMAIL", "")
GOOGLE_VOICE_PASSWORD = os.environ.get("GOOGLE_VOICE_PASSWORD", "")
GOOGLE_VOICE_FORWARDING = os.environ.get("GOOGLE_VOICE_FORWARDING", "")


class CredlocityDialer:
    """
    Google Voice Dialer for Credlocity Collections
    Handles outbound calls and SMS messages
    """
    
    def __init__(self):
        self.voice = None
        self.logged_in = False
        self.email = GOOGLE_VOICE_EMAIL
        self.password = GOOGLE_VOICE_PASSWORD
        self.forwarding_number = GOOGLE_VOICE_FORWARDING
        
    def login(self) -> bool:
        """Attempt to login to Google Voice"""
        if not self.email or not self.password:
            logger.warning("Google Voice credentials not configured")
            return False
            
        try:
            from googlevoice import Voice
            self.voice = Voice()
            self.voice.login(email=self.email, passwd=self.password)
            self.logged_in = True
            logger.info(f"Successfully logged into Google Voice as {self.email}")
            return True
        except ImportError:
            logger.error("pygooglevoice not installed")
            return False
        except Exception as e:
            logger.error(f"Failed to login to Google Voice: {str(e)}")
            return False
    
    def make_call(self, phone_number: str, forwarding_number: Optional[str] = None) -> Tuple[bool, str]:
        """
        Initiate a call via Google Voice
        
        Args:
            phone_number: The number to call
            forwarding_number: Your phone number that will ring first (optional, uses default)
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        if not self.logged_in:
            if not self.login():
                return False, "Google Voice not configured or login failed"
        
        forward_to = forwarding_number or self.forwarding_number
        if not forward_to:
            return False, "No forwarding number configured. Please set GOOGLE_VOICE_FORWARDING in environment."
        
        try:
            # Clean phone number - remove non-digits except leading +
            clean_number = ''.join(c for c in phone_number if c.isdigit() or c == '+')
            if not clean_number.startswith('+') and not clean_number.startswith('1'):
                clean_number = '1' + clean_number  # Add US country code
                
            clean_forward = ''.join(c for c in forward_to if c.isdigit() or c == '+')
            if not clean_forward.startswith('+') and not clean_forward.startswith('1'):
                clean_forward = '1' + clean_forward
            
            logger.info(f"Initiating call to {clean_number}, forwarding to {clean_forward}")
            self.voice.call(clean_number, clean_forward)
            
            return True, f"Call initiated to {phone_number}. Your phone ({forward_to}) will ring shortly."
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to make call: {error_msg}")
            return False, f"Call failed: {error_msg}"
    
    def send_sms(self, phone_number: str, message: str) -> Tuple[bool, str]:
        """
        Send SMS via Google Voice
        
        Args:
            phone_number: The number to text
            message: The message to send
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        if not self.logged_in:
            if not self.login():
                return False, "Google Voice not configured or login failed"
        
        if not message or len(message.strip()) < 1:
            return False, "Message cannot be empty"
            
        try:
            # Clean phone number
            clean_number = ''.join(c for c in phone_number if c.isdigit() or c == '+')
            if not clean_number.startswith('+') and not clean_number.startswith('1'):
                clean_number = '1' + clean_number
            
            logger.info(f"Sending SMS to {clean_number}: {message[:50]}...")
            self.voice.send_sms(clean_number, message)
            
            return True, f"SMS sent to {phone_number}"
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to send SMS: {error_msg}")
            return False, f"SMS failed: {error_msg}"
    
    def get_status(self) -> dict:
        """Get the current status of the Google Voice integration"""
        return {
            "configured": bool(self.email and self.password),
            "logged_in": self.logged_in,
            "email": self.email[:3] + "***" + self.email[-10:] if self.email else None,
            "forwarding_configured": bool(self.forwarding_number),
            "forwarding_number": self.forwarding_number[:3] + "***" + self.forwarding_number[-4:] if self.forwarding_number else None
        }


# Singleton instance
_dialer_instance = None

def get_dialer() -> CredlocityDialer:
    """Get or create the singleton dialer instance"""
    global _dialer_instance
    if _dialer_instance is None:
        _dialer_instance = CredlocityDialer()
    return _dialer_instance
