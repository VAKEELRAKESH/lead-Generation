import re

from config.constants import EMAIL_REGEX


INVALID_EXTENSIONS = [
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".svg",
    ".gif"
]


def is_valid_email(email):

    email = email.lower().strip()

    # remove image names
    for ext in INVALID_EXTENSIONS:

        if email.endswith(ext):
            return False

    # must contain @ and .
    if "@" not in email:
        return False

    if "." not in email:
        return False

    return True


def extract_emails(html):

    emails = re.findall(
        EMAIL_REGEX,
        html
    )

    cleaned_emails = []

    for email in emails:

        if is_valid_email(email):

            cleaned_emails.append(email)

    unique_emails = list(set(cleaned_emails))

    return unique_emails