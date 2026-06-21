import urllib.request
from pathlib import Path

# Configuration
FONTS = [
    "Roboto",
    "Open Sans",
    "Montserrat",
    "Poppins",
]
TARGET_DIR = Path("assets/fonts")


def download_and_extract(font_name):
    print(f"----- Processing {font_name} -----")

    # Map common names to folder names on GitHub (google/fonts/ofl/...)
    font_map = {
        "Roboto": "roboto",
        "Open Sans": "opensans",
        "Montserrat": "montserrat",
        "Poppins": "poppins",
    }

    folder = font_map.get(font_name)
    if not folder:
        print(f"Skipping {font_name}, map not found")
        return

    extract_dir = TARGET_DIR / font_name

    if not extract_dir.exists():
        extract_dir.mkdir(parents=True)
        print(f"Created: {extract_dir.absolute()}")
    else:
        print(f"Exists: {extract_dir.absolute()}")

    print(f"Processing {font_name}...")

    base_url = f"https://github.com/google/fonts/raw/main/ofl/{folder}/"

    # Filename patterns often strip spaces
    font_name.replace(" ", "")

    # Standard weights to look for
    weights = ["Regular", "Bold", "Italic", "Medium", "SemiBold", "Light"]

    files_to_check = []

    if font_name == "Open Sans":
        # Open Sans on GitHub is often OpenSans-Variable or static/OpenSans-...
        # We will try to get static TTFs
        for w in weights:
            files_to_check.append(f"static/OpenSans-{w}.ttf")

    elif font_name == "Montserrat":
        for w in weights:
            files_to_check.append(f"static/Montserrat-{w}.ttf")

    elif font_name == "Roboto":
        # Roboto is usually in root
        for w in weights:
            files_to_check.append(f"Roboto-{w}.ttf")

    elif font_name == "Poppins":
        for w in weights:
            files_to_check.append(f"Poppins-{w}.ttf")

    for filename in files_to_check:
        # Check if we should try root if static fails, or vice versa?
        # We constructed specific paths above.

        url = f"{base_url}{filename}"
        local_name = Path(filename).name  # Flatten structure
        dest = extract_dir / local_name

        try:
            print(f"  Downloading {filename}...")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as response:
                with open(dest, "wb") as f:
                    f.write(response.read())
                print("    Success")
        except Exception:
            # Try static/ prefix if not already there
            if "static/" not in filename:
                try:
                    url = f"{base_url}static/{filename}"
                    print(f"    Trying static/{filename}...")
                    req = urllib.request.Request(
                        url, headers={"User-Agent": "Mozilla/5.0"}
                    )
                    with urllib.request.urlopen(req) as response:
                        with open(dest, "wb") as f:
                            f.write(response.read())
                        print("    Success (from static)")
                except Exception:
                    print(f"    Failed: {url}")
            else:
                print(f"    Failed: {url}")


def main():
    if not TARGET_DIR.exists():
        TARGET_DIR.mkdir(parents=True)

    for font in FONTS:
        download_and_extract(font)

    print("\nAll downloads finished.")


if __name__ == "__main__":
    main()
