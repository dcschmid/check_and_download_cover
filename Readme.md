# Album Cover and Artist Image Fetcher

This project is designed to download album covers from multiple sources such as Spotify, Deezer, Last.fm, Discogs, and MusicBrainz. If no album cover is found, a default cover image is used instead.

## Features

- Fetches album covers from various sources: Spotify, Deezer, Last.fm, Discogs, and MusicBrainz.
- Uses a default cover image (/default-cover.jpg) when no album cover is found.
- Resizes images to 300x300 pixels before saving.
- Generates JSON files with album cover information.

## Setup

1. Clone the repository:

```bash
git clone https://github.com/itskayla/album-cover-fetcher.git
cd album-cover-fetcher
```

2. Create and activate a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

3. Install the required dependencies:

```bash
pip install -r requirements.txt
```

4. Create the necessary directories:

Make sure you have the following directories ready to store downloaded images:

```bash
mkdir bandcover
````

5. Prepare your input JSON:

The JSON file should contain an array of album objects with fields like artist, album, year, and optionally coverSrc.

```json
[
    {
        "artist": "Fela Kuti",
        "album": "Zombie",
        "year": "1976",
        "coverSrc": ""
    },
    {
        "artist": "Burna Boy",
        "album": "African Giant",
        "year": "2019"
    }
]
```

## Environment Variables

Create a .env file in your project directory with the following API keys. This script relies on external APIs, so make sure to get API credentials from the respective platforms.

``` bash
SPOTIFY_CLIENT_ID=<your_spotify_client_id>
SPOTIFY_CLIENT_SECRET=<your_spotify_client_secret>
DEEZER_API_TOKEN=<your_deezer_api_token>
LASTFM_API_KEY=<your_lastfm_api_key>
DISCOGS_API_TOKEN=<your_discogs_token>
```

## Usage

Once everything is set up, run the script with the path to your JSON file:

```bash
python check_and_download_cover.py <path_to_json_file>
```

For example:

```bash
python check_and_download_cover.py ./json/albums.json
```

The script will check for missing album covers and fetch them from various sources. If no album cover is found, it will try to get an artist image and save it.

## Sources and Logic

1. Spotify:

- The script first attempts to authenticate with Spotify and fetch the album cover using the artist and album name. The album types (album, ep, compilation, live) are taken into consideration.

2. Deezer:

- Similar to Spotify, it searches for the album cover on Deezer based on the artist and album name.

3. Last.fm

- The script makes a call to the Last.fm API to find the album cover.

4. Discogs

- Discogs API is used to fetch the album cover based on the artist and album metadata.

5. MusicBrainz/Cover Art Archive:

- Finally, it tries to fetch the album cover from MusicBrainz. If the cover is not found or returns a 404, it proceeds to fetch an artist image.

## Notes

- Rate Limiting: The script includes a rate_limit() function to prevent overloading the API with too many requests. By default, there is a 2-second delay between API calls.

- Image Conversion: If an image has an alpha channel (RGBA), it is automatically converted to RGB to avoid issues when saving the image as JPEG.

- File Structure: Album cover and artist images are stored in the bandcover/`<genre>` directory, with filenames slugified to avoid special characters.

- Error Handling: The script logs errors when requests fail or covers are not found, ensuring the process can continue without interruptions.
