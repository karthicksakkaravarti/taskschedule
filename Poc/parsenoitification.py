import requests
from bs4 import BeautifulSoup

# Target URL
URL = "https://apply.tnpscexams.in/notification?app_id=UElZMDAwMDAwMQ=="

# Headers to mimic a browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

# Request the page
response = requests.get(URL, headers=HEADERS)
if response.status_code != 200:
    print(f"Error: Unable to access page. Status code {response.status_code}")
    exit()

# Parse the page
soup = BeautifulSoup(response.content, "html.parser")

# Find the table
table = soup.find("table")

# Extract rows
rows = table.find_all("tr")[1:]  # Skip header

notifications = []

for row in rows:
    cols = row.find_all("td")
    if len(cols) >= 8:
        notification = {
            "notification_no": cols[0].text.strip(),
            "notification_date": cols[1].text.strip(),
            "post_name": cols[2].text.strip(),
            "app_start": cols[3].text.strip(),
            "app_end": cols[4].text.strip(),
            "payment_last_date": cols[5].text.strip(),
            "languages": cols[6].text.strip(),
            "exam_date": cols[7].text.strip(),
            "status": cols[8].text.strip() if len(cols) > 8 else "N/A"
        }
        notifications.append(notification)

# Display results
for job in notifications:
    print(f"{job['notification_no']} | {job['post_name']} | Last Date: {job['app_end']} | Status: {job['status']}")
