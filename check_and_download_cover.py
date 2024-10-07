import os
import json
import requests
import logging
from PIL import Image
from io import BytesIO
from slugify import slugify
from fuzzywuzzy import fuzz
import base64
import time
import urllib.parse
import discogs_client
import unicodedata

# Set up logging to capture errors and missing covers
logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
DEEZER_API_URL = "https://api.deezer.com/"
DISCOGS_API_TOKEN = os.getenv("DISCOGS_API_TOKEN")
MUSICBRAINZ_API_URL = "https://musicbrainz.org/ws/2/"
LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")

# Common title variants to improve search results
TITLE_VARIANTS = ["Deluxe", "Remastered", "Anniversary", "Special Edition", "Expanded Edition"]
ALBUM_TYPES = ["album", "ep", "compilation", "live"]

def rate_limit(delay: float = 2.0) -> None:
    """
    Rate limit to avoid exceeding API call limits.

    Args:
        delay (float, optional): The time in seconds to wait between API calls. Defaults to 2.0.
    """
    time.sleep(delay)

def authenticate_spotify():
    """
    Authenticate with Spotify using client ID and secret.

    Returns a Spotify API token to be used for authentication.
    """
    # Construct the authentication header
    auth_url = "https://accounts.spotify.com/api/token"
    auth_header = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()

    # Set up the request headers and data
    headers = {"Authorization": f"Basic {auth_header}"}
    data = {"grant_type": "client_credentials"}

    # Perform the POST request
    response = requests.post(auth_url, headers=headers, data=data)

    # Check for a successful response
    if response.status_code == 200:
        # Return the Spotify token
        return response.json().get("access_token")

    # Log the error if authentication fails
    logging.error(f"Spotify authentication failed: {response.status_code} - {response.text}")
    return None

def fuzzy_match(target: str, candidate: str, threshold: int = 85) -> bool:
    """
    Perform a fuzzy match between two strings using the token sort ratio algorithm.

    Args:
        target (str): The target string to compare against.
        candidate (str): The candidate string to compare with the target.
        threshold (int, optional): The minimum similarity score to consider a match. Defaults to 85.

    Returns:
        bool: True if the fuzzy match ratio between the target and candidate exceeds the threshold, False otherwise.
    """
    return fuzz.token_sort_ratio(target, candidate) >= threshold

def normalize_artist_name(artist: str) -> str:
    """
    Normalize the artist name by removing accents and special characters.

    This function is used to normalize artist names to remove any non-ASCII
    characters that may affect the accuracy of the fuzzy string matching.

    Args:
        artist (str): The artist name to normalize.

    Returns:
        str: The normalized artist name.
    """
    # Normalize the string using the NFD (Compatibility Decomposition) form
    normalized = unicodedata.normalize('NFD', artist)
    # Remove any special characters or accents
    return ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')

def get_spotify_artist_id(artist: str, spotify_token: str) -> str | None:
    """
    Fetch the Spotify artist ID using the artist's name.

    Args:
        artist (str): The artist name to search for.
        spotify_token (str): The Spotify API token to use for authentication.

    Returns:
        str | None: The Spotify artist ID if found, or None if not.
    """
    headers = {"Authorization": f"Bearer {spotify_token}"}
    search_url = "https://api.spotify.com/v1/search"
    params = {"q": f"artist:{artist}", "type": "artist", "limit": 1}

    response = requests.get(search_url, headers=headers, params=params)
    rate_limit()

    if response.status_code == 200:
        data = response.json()
        if data['artists']['items']:
            # Get the first matching artist ID
            artist_id = data['artists']['items'][0]['id']
            return artist_id
        else:
            logging.error(f"No artist found on Spotify for '{artist}'")
    else:
        logging.error(f"Failed to fetch artist ID from Spotify for '{artist}'. Status code: {response.status_code}")

    return None

def fetch_cover_spotify(artist: str, album: str, spotify_token: str, release_year: str | None = None) -> str | None:
    """
    Fetch cover URL from Spotify with stricter verification, considering album types.

    Args:
        artist (str): The artist name to search for.
        album (str): The album name to search for.
        spotify_token (str): The Spotify API token to use for authentication.
        release_year (str | None, optional): The release year of the album to search for. Defaults to None.

    Returns:
        str | None: The Spotify album cover URL if found, or None if not.
    """
    headers = {"Authorization": f"Bearer {spotify_token}"}
    search_url = "https://api.spotify.com/v1/search"

    for variant in [album] + [f"{album} {suffix}" for suffix in TITLE_VARIANTS]:
        params = {"q": f"album:{variant} artist:{artist}", "type": "album"}
        response = requests.get(search_url, headers=headers, params=params)
        rate_limit()

        if response.status_code == 200:
            data = response.json()
            if data['albums']['items']:
                for album_data in data['albums']['items']:
                    album_name = album_data['name']
                    artist_name = album_data['artists'][0]['name']
                    album_type = album_data.get('album_type')
                    album_release_date = album_data.get('release_date', '').split('-')[0]  # Extract year

                    # Validate the album type (album, ep, compilation, live)
                    if (fuzzy_match(artist, artist_name, threshold=90) and
                            fuzzy_match(album, album_name) and
                            album_type in ALBUM_TYPES and
                            (release_year is None or album_release_date == release_year)):
                        logging.info(f"Found matching cover on Spotify for '{album}' by '{artist}'")
                        return album_data['images'][0]['url']  # Get the largest image
        else:
            logging.error(f"Failed to fetch from Spotify. Status code: {response.status_code}")

    return None

def fetch_cover_deezer(artist: str, album: str, release_year: str | None = None) -> str | None:
    """Fetch cover URL from Deezer with stricter verification, considering album types.

    Args:
        artist (str): The artist name to search for.
        album (str): The album name to search for.
        release_year (str | None, optional): The release year of the album to search for. Defaults to None.

    Returns:
        str | None: The Deezer album cover URL if found, or None if not.
    """
    # Iterate through the given album title and its variants (e.g. "The Dark Side of the Moon" and "The Dark Side of the Moon (Deluxe Edition)")
    for album_variant in [album] + [f"{album} {suffix}" for suffix in TITLE_VARIANTS]:
        # Construct the API URL with the query parameters
        response = requests.get(f"{DEEZER_API_URL}search/album?q=artist:'{artist}' album:'{album_variant}'")
        rate_limit()  # Avoid hitting the rate limit

        # Check if the API call was successful
        if response.status_code == 200:
            data = response.json()
            if data['data']:  # Check if the API returned any data
                album_data = data['data'][0]
                album_name = album_data['title']
                artist_name = album_data['artist']['name']
                album_type = album_data.get('record_type')
                album_release_date = album_data.get('release_date', '').split('-')[0]  # Extract year

                # Validate the album type (album, ep, compilation, live)
                if (fuzzy_match(artist, artist_name, threshold=90) and
                        fuzzy_match(album, album_name) and
                        album_type in ALBUM_TYPES and
                        (release_year is None or album_release_date == release_year)):
                    logging.info(f"Found matching cover on Deezer for '{album}' by '{artist}'")
                    return album_data['cover_big']  # Get the largest image
        else:
            logging.error(f"Failed to fetch from Deezer. Status code: {response.status_code}")

    return None

def fetch_cover_lastfm(artist: str, album: str) -> str | None:
    """Fetch cover URL from Last.fm.

    Args:
        artist (str): The artist name to search for.
        album (str): The album name to search for.

    Returns:
        str | None: The URL of the album cover if found, or None if not.
    """
    url = f"http://ws.audioscrobbler.com/2.0/"
    params = {
        'method': 'album.getinfo',
        'api_key': LASTFM_API_KEY,
        'artist': artist,
        'album': album,
        'format': 'json'
    }

    response = requests.get(url, params=params)
    rate_limit()

    if response.status_code == 200:
        data = response.json()
        if 'album' in data and 'image' in data['album']:
            images = data['album']['image']
            for img in images:
                if img['size'] == 'extralarge':  # We prefer the extralarge size
                    logging.info(f"Found cover on Last.fm for '{album}' by '{artist}'")
                    return img['#text']
    logging.info(f"No matches found on Last.fm for '{album}' by '{artist}'")
    return None

def fetch_cover_discogs(artist, album):
    """Fetch cover URL from Discogs with stricter verification.

    We use the Discogs API to search for the album by the given artist and
    album name. We then extract the first image from the first result and
    return its URL.

    Args:
        artist (str): The artist name to search for.
        album (str): The album name to search for.

    Returns:
        str | None: The URL of the album cover if found, or None if not.
    """
    discogs_api = discogs_client.Client('MusicTriviaApp', user_token=DISCOGS_API_TOKEN)
    try:
        results = discogs_api.search(album, artist=artist, type='release')
        rate_limit()

        if results.count > 0:
            release = results[0]
            return release.images[0]['uri']
    except Exception as e:
        logging.error(f"Error fetching cover from Discogs for '{album}' by '{artist}': {e}")
    return None

def fetch_cover_musicbrainz(artist, album):
    """Fetch cover URL from MusicBrainz.

    We use the MusicBrainz API to search for the album by the given artist and
    album name. We then extract the first result and use the release ID to
    construct a URL for the cover art on the Cover Art Archive. We then check
    if the image is available by making a HEAD request and return the URL if
    it is.

    Args:
        artist (str): The artist name to search for.
        album (str): The album name to search for.

    Returns:
        str | None: The URL of the album cover if found, or None if not.
    """
    headers = {'User-Agent': 'MusicTriviaApp/1.0 (example@example.com)'}
    query = f"artist:{artist} AND release:{album}"
    params = {'query': query, 'fmt': 'json', 'limit': 1}

    response = requests.get(f"{MUSICBRAINZ_API_URL}release", headers=headers, params=params)
    rate_limit()

    if response.status_code == 200:
        data = response.json()
        if 'releases' in data and len(data['releases']) > 0:
            release_id = data['releases'][0]['id']
            cover_url = f"https://coverartarchive.org/release/{release_id}/front-500"

            # Check if the image is available before returning the URL
            head_response = requests.head(cover_url)
            if head_response.status_code == 404:
                logging.error(f"Cover not found on Cover Art Archive for '{album}' by '{artist}'. HTTP Status: 404")
                return None
            logging.info(f"Found cover on MusicBrainz for '{album}' by '{artist}'")
            return cover_url

    logging.info(f"No matches found in MusicBrainz for '{album}' by '{artist}'")
    return None

def download_and_resize_image(url: str, output_path: str) -> bool:
    """Download an image from the given URL and resize it to 300x300 pixels.

    Args:
        url (str): The URL of the image to download.
        output_path (str): The path to save the resized image.

    Returns:
        bool: True if the image was downloaded and resized successfully, False otherwise.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            # Read the image from the response content
            img = Image.open(BytesIO(response.content))

            # Resize the image to 300x300 pixels
            img = img.resize((300, 300))

            # Convert 'RGBA' mode to 'RGB' to save as JPEG
            if img.mode == 'RGBA':
                img = img.convert('RGB')

            # Ensure directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            # Save the resized image to the given path
            img.save(output_path)
        else:
            logging.error(f"Failed to download image from {url}. HTTP Status: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        logging.error(f"Error while downloading image from {url}: {e}")
        return False
    return True

def process_json(file_path):
    """Process the JSON file, checking for missing covers and downloading them."""
    spotify_token = authenticate_spotify()

    json_filename = os.path.basename(file_path)
    genre = os.path.splitext(json_filename)[0]

    with open(file_path, 'r') as file:
        data = json.load(file)

    for album_data in data:
        artist = album_data['artist']
        album = album_data['album']
        release_year = album_data.get('year')
        cover_src = album_data.get('coverSrc')

        # Add coverSrc field if missing
        if not cover_src:
            album_data['coverSrc'] = ""

        slugified_filename = slugify(f"{artist}_{album}") + ".jpg"
        output_path = os.path.join("bandcover", genre, slugified_filename)

        if cover_src and os.path.exists(cover_src):
            continue

        if os.path.exists(output_path):
            album_data['coverSrc'] = f"/{output_path}"
            continue

        # Try to fetch the cover from different sources
        cover_url = None
        logging.info(f"Attempting to fetch cover for '{album}' by '{artist}'")

        # Spotify
        if spotify_token:
            cover_url = fetch_cover_spotify(artist, album, spotify_token, release_year)
            if cover_url:
                logging.info(f"Found cover for '{album}' by '{artist}' on Spotify.")

        # Deezer
        if not cover_url:
            cover_url = fetch_cover_deezer(artist, album, release_year)
            if cover_url:
                logging.info(f"Found cover for '{album}' by '{artist}' on Deezer.")

        # Last.fm
        if not cover_url:
            cover_url = fetch_cover_lastfm(artist, album)
            if cover_url:
                logging.info(f"Found cover for '{album}' by '{artist}' on Last.fm.")

        # Discogs
        if not cover_url:
            cover_url = fetch_cover_discogs(artist, album)
            if cover_url:
                logging.info(f"Found cover for '{album}' by '{artist}' on Discogs.")

        # MusicBrainz/Cover Art Archive
        if not cover_url:
            cover_url = fetch_cover_musicbrainz(artist, album)
            if cover_url:
                logging.info(f"Found cover for '{album}' by '{artist}' on Cover Art Archive.")
            else:
                logging.error(f"Cover not found on Cover Art Archive for '{album}' by '{artist}'")
                # If no cover is found, use the default cover image
                logging.info(f"Using default cover image for '{album}' by '{artist}'")
                album_data['coverSrc'] = "/default-cover.jpg"

        # Download and resize image if cover URL found
        if cover_url:
            if not download_and_resize_image(cover_url, output_path):
                logging.error(f"Could not download cover for '{album}' by '{artist}'")
            else:
                album_data['coverSrc'] = f"/{output_path}"

    # Save the updated JSON
    with open(file_path, 'w') as file:
        json.dump(data, file, indent=2)

    logging.info(f"Updated JSON saved to {file_path}")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Check and download missing album covers.")
    parser.add_argument("file_path", help="Path to the JSON file")
    args = parser.parse_args()

    process_json(args.file_path)
