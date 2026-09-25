"""
Helper script to generate and save GOOGLE_REFRESH_TOKEN for Miles.

Usage:
    python scripts/get_refresh_token.py
"""

import os
import sys
import webbrowser
from pathlib import Path
from urllib.parse import urlencode, parse_qs, urlparse

try:
    from dotenv import load_dotenv
    import httpx
except ImportError:
    print("Please install httpx and python-dotenv first:")
    print("pip install httpx python-dotenv")
    sys.exit(1)

# Paths
APP_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = APP_DIR.parent
ENV_APP = APP_DIR / ".env"
ENV_ROOT = ROOT_DIR / ".env"

load_dotenv(ENV_APP)

CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/calendar.events",
]

def update_env_file(filepath: Path, key: str, value: str):
    if not filepath.exists():
        return
    content = filepath.read_text(encoding="utf-8")
    lines = content.splitlines()
    found = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{key}="):
            new_lines.append(f"{key}={value}")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key}={value}")
    filepath.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"Updated {key} in {filepath}")

def main():
    print("=" * 60)
    print(" Miles - Google Refresh Token Generator")
    print("=" * 60)

    if not CLIENT_ID or not CLIENT_SECRET:
        print("ERROR: GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in .env")
        sys.exit(1)

    print(f"Client ID: {CLIENT_ID[:20]}...")
    print("\nWe will use Google's OAuth 2.0 flow to generate your Refresh Token.")
    print("Choose an option:")
    print(" 1) Generate via Google OAuth Playground (Recommended, requires no extra redirect URI)")
    print(" 2) Paste an authorization code from browser redirect")
    
    choice = input("\nEnter choice [1 or 2, default 1]: ").strip() or "1"

    if choice == "1":
        print("\nFollow these 4 simple steps:")
        print("1. In Google Cloud Console, ensure this exact redirect URI is added to your OAuth client:")
        print("   https://developers.google.com/oauthplayground")
        print("2. Open: https://developers.google.com/oauthplayground")
        print("3. Click the Gear Icon (⚙️) on top right:")
        print("   - Check 'Use your own OAuth credentials'")
        print(f"   - OAuth Client ID: {CLIENT_ID}")
        print(f"   - OAuth Client secret: {CLIENT_SECRET}")
        print("4. On the left side:")
        print("   - Under 'Input your own scopes', paste:")
        print(f"     {' '.join(SCOPES)}")
        print("   - Click 'Authorize APIs'")
        print("   - Grant consent")
        print("   - Click 'Exchange authorization code for tokens'")
        print("   - Copy the Refresh token\n")
        
        token = input("Paste your Refresh token here: ").strip()
        if not token:
            print("No token provided. Aborted.")
            return

        update_env_file(ENV_APP, "GOOGLE_REFRESH_TOKEN", token)
        if ENV_ROOT.exists():
            update_env_file(ENV_ROOT, "GOOGLE_REFRESH_TOKEN", token)
        print("\nSUCCESS! Google Refresh Token has been saved to your .env files.")
    else:
        redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "https://miles-one-nu.vercel.app/")
        params = {
            "client_id": CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "prompt": "consent",
        }
        auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
        print(f"\nOpening browser to authorize:\n{auth_url}\n")
        try:
            webbrowser.open(auth_url)
        except Exception:
            pass
        
        print("After authorizing, your browser will redirect to your redirect URI with a ?code= parameter.")
        redirected_url = input("\nPaste the full redirected URL (or just the code): ").strip()
        if not redirected_url:
            print("No code provided. Aborted.")
            return

        code = redirected_url
        if "code=" in redirected_url:
            parsed = urlparse(redirected_url)
            qs = parse_qs(parsed.query)
            code = qs.get("code", [redirected_url])[0]

        print(f"Exchanging code for tokens...")
        resp = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
        )

        if resp.status_code != 200:
            print(f"Failed to exchange code: {resp.status_code} - {resp.text}")
            return

        tokens = resp.json()
        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            print("Warning: Google did not return a refresh_token (did you approve consent?). Response:")
            print(tokens)
            return

        update_env_file(ENV_APP, "GOOGLE_REFRESH_TOKEN", refresh_token)
        if ENV_ROOT.exists():
            update_env_file(ENV_ROOT, "GOOGLE_REFRESH_TOKEN", refresh_token)
        print(f"\nSUCCESS! Refresh Token retrieved and saved to .env files: {refresh_token[:15]}...")

if __name__ == "__main__":
    main()
