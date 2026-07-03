import os


def create_folders():

    os.makedirs("html", exist_ok=True)
    os.makedirs("output", exist_ok=True)
    os.makedirs("logs", exist_ok=True)


def save_html(filename, html):

    with open(
        f"html/{filename}.html",
        "w",
        encoding="utf-8"
    ) as file:

        file.write(html)


def clean_filename(url):

    filename = (
        url.replace("https://", "")
        .replace("http://", "")
        .replace("/", "_")
        .replace("?", "_")
        .replace("&", "_")
    )

    return filename