#!/usr/bin/env python3

import argparse
import pyotp
import qrcode
from urllib.parse import urlparse, parse_qs
import sys
import time

# Optional imports for QR code processing
try:
    import cv2
    from pyzbar import pyzbar
    QR_PROCESSING_AVAILABLE = True
except ImportError:
    QR_PROCESSING_AVAILABLE = False

def extract_qr_from_image(image_path):
    """Extract QR code data from an image file."""
    if not QR_PROCESSING_AVAILABLE:
        raise ImportError("QR code processing requires opencv-python and pyzbar. Install with: pip install opencv-python pyzbar")

    try:
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"Could not load image: {image_path}")

        # Decode QR codes in the image
        qr_codes = pyzbar.decode(image)

        if not qr_codes:
            raise ValueError("No QR codes found in the image")

        # Return the first QR code's data
        return qr_codes[0].data.decode('utf-8')

    except Exception as e:
        raise ValueError(f"Error processing image: {str(e)}")

def parse_otpauth_url(otpauth_url):
    """Parse an otpauth:// URL and extract OTP parameters."""
    try:
        parsed = urlparse(otpauth_url)

        if parsed.scheme != 'otpauth':
            raise ValueError("URL must start with 'otpauth://'")

        # Extract type (totp or hotp)
        otp_type = parsed.netloc.lower()
        if otp_type not in ['totp', 'hotp']:
            raise ValueError(f"Unsupported OTP type: {otp_type}")

        # Extract account name from path
        account = parsed.path.lstrip('/')

        # Parse query parameters
        params = parse_qs(parsed.query)

        # Extract secret (required)
        if 'secret' not in params:
            raise ValueError("Secret parameter is required")
        secret = params['secret'][0]

        # Extract optional parameters
        issuer = params.get('issuer', [''])[0]
        algorithm = params.get('algorithm', ['SHA1'])[0].upper()
        digits = int(params.get('digits', ['6'])[0])
        period = int(params.get('period', ['30'])[0])
        counter = int(params.get('counter', ['0'])[0])

        return {
            'type': otp_type,
            'account': account,
            'secret': secret,
            'issuer': issuer,
            'algorithm': algorithm,
            'digits': digits,
            'period': period,
            'counter': counter
        }

    except Exception as e:
        raise ValueError(f"Error parsing otpauth URL: {str(e)}")

def generate_otp(otp_params):
    """Generate OTP code based on parameters."""
    try:
        import hashlib

        # Map algorithm names to hashlib functions
        algorithm_map = {
            'SHA1': hashlib.sha1,
            'SHA256': hashlib.sha256,
            'SHA512': hashlib.sha512
        }

        digest = algorithm_map.get(otp_params['algorithm'], hashlib.sha1)

        if otp_params['type'] == 'totp':
            totp = pyotp.TOTP(
                otp_params['secret'],
                digits=otp_params['digits'],
                digest=digest,
                interval=otp_params['period']
            )
            return totp.now()

        elif otp_params['type'] == 'hotp':
            hotp = pyotp.HOTP(
                otp_params['secret'],
                digits=otp_params['digits'],
                digest=digest
            )
            return hotp.at(otp_params['counter'])

    except Exception as e:
        raise ValueError(f"Error generating OTP: {str(e)}")

# Library functions for easy import
def get_otp_from_url(otpauth_url):
    """
    Simple function to get OTP code from otpauth URL.

    Args:
        otpauth_url (str): The otpauth:// URL

    Returns:
        str: The current OTP code

    Raises:
        ValueError: If URL is invalid or OTP generation fails
    """
    otp_params = parse_otpauth_url(otpauth_url)
    return generate_otp(otp_params)

def get_otp_from_image(image_path):
    """
    Simple function to get OTP code from QR code image.

    Args:
        image_path (str): Path to the QR code image

    Returns:
        str: The current OTP code

    Raises:
        ImportError: If QR processing dependencies are not available
        ValueError: If image processing fails or OTP generation fails
    """
    otpauth_url = extract_qr_from_image(image_path)
    return get_otp_from_url(otpauth_url)

def get_otp_info(otpauth_url):
    """
    Get detailed OTP information from otpauth URL.

    Args:
        otpauth_url (str): The otpauth:// URL

    Returns:
        dict: Dictionary containing OTP parameters and current code
    """
    otp_params = parse_otpauth_url(otpauth_url)
    otp_code = generate_otp(otp_params)

    result = otp_params.copy()
    result['current_otp'] = otp_code

    # Add time remaining for TOTP
    if otp_params['type'] == 'totp':
        remaining = otp_params['period'] - (int(time.time()) % otp_params['period'])
        result['time_remaining'] = remaining

    return result

def main():
    parser = argparse.ArgumentParser(description='Extract and generate OTP from QR codes or otpauth URLs')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-i', '--image', help='Path to QR code image file')
    group.add_argument('-u', '--url', help='otpauth:// URL')
    parser.add_argument('-v', '--verbose', action='store_true', help='Show detailed information')

    args = parser.parse_args()

    try:
        # Extract otpauth URL
        if args.image:
            print(f"Extracting QR code from image: {args.image}")
            otpauth_url = extract_qr_from_image(args.image)
            print(f"Found otpauth URL: {otpauth_url}")
        else:
            otpauth_url = args.url

        # Parse the otpauth URL
        otp_params = parse_otpauth_url(otpauth_url)

        if args.verbose:
            print(f"\nOTP Parameters:")
            print(f"  Type: {otp_params['type'].upper()}")
            print(f"  Account: {otp_params['account']}")
            print(f"  Issuer: {otp_params['issuer']}")
            print(f"  Algorithm: {otp_params['algorithm']}")
            print(f"  Digits: {otp_params['digits']}")
            if otp_params['type'] == 'totp':
                print(f"  Period: {otp_params['period']} seconds")
            else:
                print(f"  Counter: {otp_params['counter']}")

        # Generate OTP
        otp_code = generate_otp(otp_params)
        print(f"\nCurrent OTP: {otp_code}")

        # For TOTP, show time remaining
        if otp_params['type'] == 'totp':
            remaining = otp_params['period'] - (int(time.time()) % otp_params['period'])
            print(f"Time remaining: {remaining} seconds")

    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()