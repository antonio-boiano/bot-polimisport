"""
OTP Generator - One-Time Password generation
Handles TOTP generation from otpauth URLs
"""

import pyotp
import time
import logging
from urllib.parse import urlparse, parse_qs
from typing import Dict

logger = logging.getLogger(__name__)


def get_otp_info(otpauth_url: str) -> Dict:
    """
    Generate OTP from otpauth URL

    Args:
        otpauth_url: OTP authentication URL (otpauth://totp/...)

    Returns:
        Dict with current_otp and time_remaining

    Example:
        >>> otp = get_otp_info("otpauth://totp/Test?secret=JBSWY3DPEHPK3PXP")
        >>> print(otp['current_otp'])  # "123456"
        >>> print(otp['time_remaining'])  # 25
    """
    try:
        parsed = urlparse(otpauth_url)
        params = parse_qs(parsed.query)

        secret = params['secret'][0]
        period = int(params.get('period', ['30'])[0])

        totp = pyotp.TOTP(secret, interval=period)
        otp_code = totp.now()
        remaining = period - (int(time.time()) % period)

        logger.debug(f"OTP generated, {remaining}s remaining")

        return {
            'current_otp': otp_code,
            'time_remaining': remaining
        }
    except Exception as e:
        logger.error(f"OTP generation failed: {e}")
        raise ValueError(f"Invalid OTP URL: {e}")


if __name__ == '__main__':
    # Test OTP generation
    logging.basicConfig(level=logging.INFO)

    # Test URL (fake secret for testing - NOT a real secret)
    # This is the well-known test secret from the TOTP RFC specification
    test_url = "otpauth://totp/Test?secret=JBSWY3DPEHPK3PXP&issuer=Test"

    print("Testing OTP generation...")
    otp_info = get_otp_info(test_url)

    print(f"✓ OTP Code: {otp_info['current_otp']}")
    print(f"✓ Time Remaining: {otp_info['time_remaining']}s")

    assert len(otp_info['current_otp']) == 6, "OTP should be 6 digits"
    assert 0 < otp_info['time_remaining'] <= 30, "Time should be valid"

    print("\n✅ OTP tests passed!")
