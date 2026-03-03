"""
Message formatters for the Agent Telegram Bot.
Bilingual (Hindi/English) message building with HTML formatting.
"""

# Emoji constants
EMOJI_CHECK = "\u2705"
EMOJI_CROSS = "\u274c"
EMOJI_CLOCK = "\u23f0"
EMOJI_BELL = "\U0001f514"
EMOJI_STAR = "\u2b50"
EMOJI_FIRE = "\U0001f525"
EMOJI_WAVE = "\U0001f44b"
EMOJI_PHONE = "\U0001f4de"
EMOJI_MEMO = "\U0001f4dd"
EMOJI_TICKET = "\U0001f3ab"
EMOJI_BOOK = "\U0001f4da"
EMOJI_CHART = "\U0001f4ca"
EMOJI_PIN = "\U0001f4cc"
EMOJI_BULB = "\U0001f4a1"
EMOJI_SHIELD = "\U0001f6e1\ufe0f"
EMOJI_PERSON = "\U0001f464"
EMOJI_ARROW = "\u27a1\ufe0f"
EMOJI_BACK = "\u2b05\ufe0f"
EMOJI_HOME = "\U0001f3e0"
EMOJI_WARN = "\u26a0\ufe0f"
EMOJI_GREEN = "\U0001f7e2"
EMOJI_RED = "\U0001f534"
EMOJI_YELLOW = "\U0001f7e1"
EMOJI_ROBOT = "\U0001f916"

# Bucket display names
BUCKET_DISPLAY = {
    "underwriting": "Underwriting",
    "finance": "Finance",
    "contest": "Contest & Engagement",
    "operations": "Operations",
    "product": "Product",
}

BUCKET_EMOJIS = {
    "underwriting": "\U0001f4cb",
    "finance": "\U0001f4b0",
    "contest": "\U0001f3c6",
    "operations": "\u2699\ufe0f",
    "product": "\U0001f4e6",
}

# Status display
STATUS_DISPLAY = {
    "received": f"{EMOJI_BELL} Received",
    "classified": f"{EMOJI_CHART} Classified",
    "routed": f"{EMOJI_ARROW} Routed to Dept",
    "pending_dept": f"{EMOJI_CLOCK} Pending Response",
    "responded": f"{EMOJI_CHECK} Responded",
    "closed": f"{EMOJI_GREEN} Closed",
}

PRIORITY_DISPLAY = {
    "critical": f"{EMOJI_RED} Critical",
    "high": f"{EMOJI_YELLOW} High",
    "medium": f"{EMOJI_BULB} Medium",
    "low": f"{EMOJI_GREEN} Low",
}


def format_welcome(agent_name: str) -> str:
    """Format welcome message after registration."""
    return (
        f"{EMOJI_WAVE} <b>Welcome, {agent_name}!</b>\n\n"
        f"Axis Max Life Agent Bot mein aapka swagat hai.\n\n"
        f"Aap yahan se:\n"
        f"{EMOJI_MEMO} /feedback — Issue ya feedback submit karein\n"
        f"{EMOJI_TICKET} /cases — Apne tickets track karein\n"
        f"{EMOJI_BOOK} /training — Product training lein\n"
        f"{EMOJI_ROBOT} /ask — Product ke baare mein kuch bhi poochein\n"
        f"{EMOJI_PERSON} /profile — Apni profile dekhein\n\n"
        f"Koi bhi help chahiye toh /help type karein."
    )


def format_profile(profile: dict) -> str:
    """Format agent profile display."""
    adm_name = profile.get("assigned_adm_name") or "Not Assigned"
    segment = profile.get("cohort_segment") or "Not Classified"
    score = profile.get("reactivation_score", 0)
    risk = profile.get("churn_risk_level") or "—"

    return (
        f"{EMOJI_PERSON} <b>Your Profile</b>\n"
        f"{'━' * 28}\n"
        f"{EMOJI_PIN} <b>Name:</b> {profile['name']}\n"
        f"{EMOJI_PHONE} <b>Phone:</b> {profile['phone']}\n"
        f"{EMOJI_PIN} <b>Location:</b> {profile['location']}\n"
        f"{EMOJI_SHIELD} <b>State:</b> {profile.get('lifecycle_state', '—')}\n"
        f"{EMOJI_STAR} <b>Engagement:</b> {profile.get('engagement_score', 0):.0f}/100\n"
        f"\n{EMOJI_CHART} <b>Cohort Analysis</b>\n"
        f"  Segment: {segment.replace('_', ' ').title()}\n"
        f"  Score: {score:.0f}/100\n"
        f"  Risk: {risk.title()}\n"
        f"\n{EMOJI_PERSON} <b>Your ADM:</b> {adm_name}\n"
        f"{'━' * 28}"
    )


def format_ticket_list(tickets: list) -> str:
    """Format list of tickets for display."""
    if not tickets:
        return f"{EMOJI_MEMO} Aapka koi ticket nahi hai abhi."

    lines = [f"{EMOJI_TICKET} <b>Your Tickets</b>\n{'━' * 28}\n"]
    for t in tickets:
        status = STATUS_DISPLAY.get(t.get("status", ""), t.get("status", ""))
        bucket = BUCKET_DISPLAY.get(t.get("bucket", ""), t.get("bucket", ""))
        emoji = BUCKET_EMOJIS.get(t.get("bucket", ""), EMOJI_MEMO)
        lines.append(
            f"{emoji} <b>{t['ticket_id']}</b>\n"
            f"  {bucket} | {status}\n"
            f"  Created: {t.get('created_at', '')[:10]}\n"
        )
    return "\n".join(lines)


def format_ticket_detail(ticket: dict) -> str:
    """Format single ticket detail with message thread."""
    status = STATUS_DISPLAY.get(ticket.get("status", ""), ticket.get("status", ""))
    bucket = BUCKET_DISPLAY.get(ticket.get("bucket", ""), ticket.get("bucket", ""))
    priority = PRIORITY_DISPLAY.get(ticket.get("priority", ""), ticket.get("priority", ""))

    lines = [
        f"{EMOJI_TICKET} <b>Ticket: {ticket['ticket_id']}</b>",
        f"{'━' * 28}",
        f"{EMOJI_PIN} <b>Department:</b> {bucket}",
        f"{EMOJI_CHART} <b>Status:</b> {status}",
        f"{EMOJI_FIRE} <b>Priority:</b> {priority}",
    ]

    if ticket.get("parsed_summary"):
        lines.append(f"\n{EMOJI_MEMO} <b>Summary:</b>\n{ticket['parsed_summary']}")

    if ticket.get("raw_feedback_text"):
        text = ticket["raw_feedback_text"][:200]
        lines.append(f"\n{EMOJI_MEMO} <b>Your Feedback:</b>\n{text}")

    if ticket.get("department_response_text"):
        lines.append(f"\n{EMOJI_CHECK} <b>Department Response:</b>\n{ticket['department_response_text']}")

    # Messages
    messages = ticket.get("messages", [])
    if messages:
        lines.append(f"\n{'━' * 28}\n{EMOJI_MEMO} <b>Conversation</b>\n")
        for msg in messages[-5:]:  # Show last 5
            sender = msg.get("sender_name", msg.get("sender_type", ""))
            text = msg.get("message_text", "")[:200]
            ts = msg.get("created_at", "")[:16]
            voice_tag = " \U0001f3a4" if msg.get("voice_file_id") else ""
            lines.append(f"<b>[{sender}]</b> {ts}{voice_tag}\n{text}\n")

    lines.append(f"\n{'━' * 28}")
    lines.append(f"Reply to this ticket: tap the button below")

    return "\n".join(lines)


def format_feedback_confirm(bucket: str, reasons: list, notes: str) -> str:
    """Format feedback confirmation before submission."""
    bucket_display = BUCKET_DISPLAY.get(bucket, bucket)
    emoji = BUCKET_EMOJIS.get(bucket, EMOJI_MEMO)
    reason_text = ", ".join(reasons) if reasons else "None selected"
    notes_text = notes[:200] if notes else "No notes"

    return (
        f"{EMOJI_MEMO} <b>Confirm Your Feedback</b>\n"
        f"{'━' * 28}\n"
        f"{emoji} <b>Department:</b> {bucket_display}\n"
        f"{EMOJI_PIN} <b>Reasons:</b> {reason_text}\n"
        f"{EMOJI_MEMO} <b>Notes:</b> {notes_text}\n"
        f"{'━' * 28}\n\n"
        f"Kya aap ye feedback submit karna chahte hain?"
    )


def format_main_menu() -> str:
    """Format main menu message."""
    return (
        f"{EMOJI_HOME} <b>Main Menu</b>\n\n"
        f"{EMOJI_MEMO} /feedback — Submit feedback / report issue\n"
        f"{EMOJI_TICKET} /cases — Track your tickets\n"
        f"{EMOJI_BOOK} /training — Product training\n"
        f"{EMOJI_ROBOT} /ask — Ask about products\n"
        f"{EMOJI_PERSON} /profile — View your profile\n"
        f"{EMOJI_BULB} /help — Get help"
    )
