def score_lead(email_count):

    if email_count >= 5:
        return "High"

    elif email_count >= 2:
        return "Medium"

    else:
        return "Low"