import os, requests, shutil, time
from bs4 import BeautifulSoup
from PIL import Image
import io # Import io to handle binary data in memory

base_raw_data_dir = "/content/my_raw_data"
classes = ['dogs', 'cats']
num_images_per_class = 200
min_image_size = (100, 100) # Define minimum image size (width, height)

# Ensure the base directory exists and is clean for a fresh run
if os.path.exists(base_raw_data_dir):
    shutil.rmtree(base_raw_data_dir)
os.makedirs(base_raw_data_dir, exist_ok=True)

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1"
}

print(f"--- Starting image download using requests and BeautifulSoup ---")

for class_name in classes:
    target_dir = os.path.join(base_raw_data_dir, class_name)
    os.makedirs(target_dir, exist_ok=True)
    print(f"\n--- Processing class: '{class_name}' ---")
    print(f"Attempting to download {num_images_per_class} images for '{class_name}' to {target_dir}...")

    image_urls = []
    page_num = 0
    # Limit to prevent excessive requests, assuming ~50 images per 'page' on Bing
    max_pages_to_check = (num_images_per_class // 50) + 10 # Get a few extra pages just in case, increased to 10

    while len(image_urls) < num_images_per_class and page_num < max_pages_to_check:
        # Bing uses 'first' parameter for pagination, where first=1 is the first image, first=51 for the 51st image, etc.
        current_first = 1 + (page_num * 50)
        search_url = f"https://www.bing.com/images/search?q={class_name}pictures&form=HDRSC3&first={current_first}"
        print(f"  Fetching search results from: {search_url} (Page {page_num + 1})")

        try:
            # Make a request to the search page
            response = requests.get(search_url, headers=headers, timeout=20)
            response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)

            # Parse the HTML content
            soup = BeautifulSoup(response.text, 'html.parser')

            found_urls_on_page = set() # Use a set to avoid duplicates within a page
            for img_tag in soup.find_all('img'):
                # Prioritize 'data-src' as it often contains the high-res image link
                if 'data-src' in img_tag.attrs:
                    img_url = img_tag['data-src']
                    if img_url.startswith('http'): # Ensure it's a full URL
                        found_urls_on_page.add(img_url)
                # Fallback to 'src' if 'data-src' is not present and it seems like a valid image URL
                elif 'src' in img_tag.attrs and img_tag['src'].startswith('http'):
                    img_url = img_tag['src']
                    # Avoid very small or generic images that might be icons/placeholders
                    if "placeholder" not in img_url.lower() and "icon" not in img_url.lower():
                        found_urls_on_page.add(img_url)

            # Add new unique URLs to the main list
            new_urls_added_this_iteration = 0
            for url in found_urls_on_page:
                if url not in image_urls: # Ensure global uniqueness across all pages
                    image_urls.append(url)
                    new_urls_added_this_iteration += 1

            print(f"  Found {len(found_urls_on_page)} potential image URLs on this page. Total unique URLs collected: {len(image_urls)}")

            # If no new URLs were found on this page and it's not the very first page, we've likely hit the end of available results.
            if new_urls_added_this_iteration == 0 and page_num > 0:
                print(f"  No new unique URLs found on page {page_num + 1}. Stopping pagination for '{class_name}'.")
                break

            page_num += 1
            if len(image_urls) < num_images_per_class: # Only sleep if more images are still needed
                time.sleep(0.1) # Small delay between page requests to avoid rate limiting

        except requests.exceptions.RequestException as e:
            print(f"An error occurred during Bing search for '{class_name}' (page {page_num + 1}): {e}")
            print("  This often indicates a network issue, website structure change, or aggressive rate limiting. Stopping pagination for this class.")
            break # Stop trying to paginate for this class if an error occurs
        except Exception as e:
            print(f"An unexpected error occurred during search or parsing for '{class_name}' (page {page_num + 1}): {e}")
            break # Stop trying to paginate for this class if an unexpected error occurs

    # After collecting URLs, proceed to download
    if not image_urls:
        print(f"  Warning: No image URLs found at all for '{class_name}' through basic HTML parsing. It's possible Bing changed its structure or blocked the request.")
        time.sleep(5) # Still wait to avoid hammering the server
        continue

    # Limit image_urls to num_images_per_class if more were found than needed
    image_urls_to_download = image_urls # We will filter by size, so don't prematurely limit.
    print(f"  Collected {len(image_urls)} potential image URLs for '{class_name}'. Attempting to download up to {num_images_per_class} unique images with size filter.")

    downloaded_count = 0
    for i, url in enumerate(image_urls_to_download):
        if downloaded_count >= num_images_per_class:
            break

        try:
            # Add a referer header to make the request more legitimate
            img_headers = headers.copy()
            img_headers['Referer'] = search_url # Use the last search URL as referer
            img_response = requests.get(url, headers=img_headers, stream=True, timeout=15)
            img_response.raise_for_status() # Raise an exception for HTTP errors

            # Read image data into memory
            image_data = io.BytesIO(img_response.content)

            # Open image with Pillow to check dimensions
            with Image.open(image_data) as img:
                width, height = img.size

                if width >= min_image_size[0] and height >= min_image_size[1]:
                    # Determine file name and path
                    file_name = url.split('/')[-1].split('?')[0]
                    if not any(file_name.lower().endswith(ext) for ext in ('.png', '.jpg', '.jpeg', '.gif')):
                        file_name = f"{class_name}_{downloaded_count}.jpg" # Default if no clear extension

                    # Prevent extremely long filenames or invalid characters if they come from the URL
                    file_name = file_name.split('#')[0] # Remove fragments
                    file_name = ''.join(c for c in file_name if c.isalnum() or c in ('.', '_', '-')) # Basic sanitization
                    if not file_name: # If sanitization makes it empty, provide a default
                        file_name = f"{class_name}_{downloaded_count}.jpg"

                    file_path = os.path.join(target_dir, file_name)

                    with open(file_path, 'wb') as f:
                        # Rewind the BytesIO object to write its content to file
                        image_data.seek(0)
                        shutil.copyfileobj(image_data, f)

                    downloaded_count += 1
                    print(f"  Downloaded {downloaded_count} image(s) for {class_name} (Dimensions: {width}x{height}).")
                    time.sleep(0.1) # Small delay between individual image downloads
                else:
                    print(f"  Skipping image from {url}: too small ({width}x{height}, min {min_image_size[0]}x{min_image_size[1]}).")

        except requests.exceptions.RequestException as e:
            print(f"  Error downloading image from {url}: {e}")
            time.sleep(1) # Shorter sleep on individual download error to keep trying
        except (Image.UnidentifiedImageError, IOError):
            # Suppress specific error message for invalid/corrupted images to reduce output noise
            time.sleep(1) # Shorter sleep for image processing errors
        except Exception as e:
            print(f"  An unexpected error occurred during image download/processing from {url}: {e}")
            time.sleep(1)

    print(f"Finished downloading for '{class_name}'. Total VALID images downloaded: {downloaded_count} out of {num_images_per_class} requested.")

    print(f"Pausing for 5 seconds before attempting to search for the next class...")
    time.sleep(5) # Reduced sleep to 5 seconds here, was 60 seconds before

# Verification step
print("\n--- Final Verification ---")
dogs_path = '/content/my_raw_data/dogs'
cats_path = '/content/my_raw_data/cats'

print(f"Contents of {dogs_path}:")
if os.path.exists(dogs_path):
    dogs_files = os.listdir(dogs_path)
    print(dogs_files)
    print(f"  Total files in {dogs_path}: {len(dogs_files)}")
else:
    print(f"Folder {dogs_path} does not exist.")

print(f"\nContents of {cats_path}:")
if os.path.exists(cats_path):
    cats_files = os.listdir(cats_path)
    print(cats_files)
    print(f"  Total files in {cats_path}: {len(cats_files)}")
else:
    print(f"Folder {cats_path} does not exist.")

print("\nSummarizing image download success:")
for class_name in classes:
    target_dir = os.path.join(base_raw_data_dir, class_name)
    if os.path.exists(target_dir):
        num_downloaded = len(os.listdir(target_dir))
        print(f"  For '{class_name}': {num_downloaded} images downloaded.")
    else:
        print(f"  For '{class_name}': Directory not created, likely no images downloaded.")
