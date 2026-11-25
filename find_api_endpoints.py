"""Developer helper: list the URLs inside the ticket site's JavaScript bundle.

Used to look for a ticket/match API that could be polled without a browser.
It sends no alerts and needs no configuration.
"""

import re

import requests

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    'Accept-Encoding': 'identity',
}

BASE = 'https://shop.royalchallengers.com'


def fetch(url):
    response = requests.get(url, headers=HEADERS, timeout=30)
    return response.content.decode('utf-8', errors='replace')


def main():
    # Step 1 — get the HTML to find the JS bundle filename
    html = fetch(f'{BASE}/ticket')

    # Step 2 — extract the main JS bundle path
    js_files = re.findall(r'/assets/index-[^"]+\.js', html)
    print(f"Found JS files: {js_files}")

    for js_path in js_files:
        js_url = BASE + js_path
        print(f"\n📦 Fetching JS bundle: {js_url}")
        js = fetch(js_url)
        print(f"   Bundle size: {len(js)} chars")

        # Step 3 — find all URLs inside the bundle
        unique_urls = sorted(set(re.findall(r'https?://[^\s\'"`,\)]{10,}', js)))

        print(f"\n🔍 All URLs found in bundle ({len(unique_urls)} unique):")
        for url in unique_urls:
            print(f"   {url}")

        # Step 4 — filter likely ticket/match API endpoints
        keywords = ['ticket', 'match', 'fixture', 'event', 'ipl', 'game', 'api', 'schedule']
        print("\n🎯 Filtered — likely ticket/data API endpoints:")
        for url in unique_urls:
            if any(k in url.lower() for k in keywords):
                print(f"   ✅ {url}")


if __name__ == "__main__":
    main()
