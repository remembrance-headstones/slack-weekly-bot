import os
from datetime import datetime, timedelta, timezone
from collections import Counter
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
channel_id = os.environ["SLACK_CHANNEL_ID"]

def ts_days_ago(days=7):
    return str((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())

def list_channels():
    """Return only channels where the bot is a member (avoid not_in_channel)."""
    chans, cursor = [], None
    try:
        while True:
            resp = client.conversations_list(
                types="public_channel",
                limit=200,
                cursor=cursor
            )
            chans += [
                c for c in resp.get("channels", [])
                if not c.get("is_archived") and c.get("is_member")
            ]
            cursor = resp.get("response_metadata", {}).get("next_cursor") or None
            if not cursor:
                break
    except SlackApiError as e:
        print("Error listing channels:", e.response.get("error"))
    return chans

def channel_messages(ch_id, oldest):
    """Safe history fetch with pagination."""
    msgs, cursor = [], None
    try:
        while True:
            resp = client.conversations_history(
                channel=ch_id,
                oldest=oldest,
                limit=200,
                cursor=cursor
            )
            msgs += resp.get("messages", [])
            cursor = resp.get("response_metadata", {}).get("next_cursor") or None
            if not cursor:
                break
    except SlackApiError as e:
        print(f"Skip {ch_id}:", e.response.get("error"))
    return msgs

def users_map():
    """Map of human users (exclude bots/deleted)."""
    users, cursor = {}, None
    try:
        while True:
            resp = client.users_list(limit=200, cursor=cursor)
            for m in resp.get("members", []):
                if not m.get("is_bot") and not m.get("deleted"):
                    users[m["id"]] = m
            cursor = resp.get("response_metadata", {}).get("next_cursor") or None
            if not cursor:
                break
    except SlackApiError as e:
        print("Error listing users:", e.response.get("error"))
    return users

def generate_report():
    oldest = ts_days_ago(7)
    users = users_map()
    by_user = Counter()
    by_channel = Counter()

    for ch in list_channels():
        msgs = channel_messages(ch["id"], oldest)

        # skip bot/app messages (HubSpot, integrations, our own posts)
        clean_msgs = []
        for m in msgs:
            if m.get("subtype") == "bot_message" or m.get("bot_id") or m.get("app_id"):
                continue
            clean_msgs.append(m)
            u = m.get("user")
            if u in users:
                by_user[u] += 1

        by_channel[ch["name"]] += len(clean_msgs)

    total_msgs = sum(by_channel.values())
    top_users = [
        (users[u]["profile"].get("real_name") or users[u].get("name") or u, c)
        for u, c in by_user.most_common(5)
    ]
    top_channels = by_channel.most_common(4)

    week_range = f"{(datetime.now()-timedelta(days=7)).strftime('%b %d')}–{datetime.now().strftime('%b %d')}"
    report = [
        f"📅 *Weekly Slack Activity — Week of {week_range}*",
        f"\n💬 Total messages: {total_msgs}",
        f"👥 Active members: {len([u for u, c in by_user.items() if c > 0])}"
    ]

    report.append("\n🏆 *Top 5 Active Users*")
    if top_users:
        for i, (name, c) in enumerate(top_users, 1):
            report.append(f"{i}️⃣ {name} — {c} msgs")
    else:
        report.append("—")

    report.append("\n📣 *Most Active Channels*")
    if top_channels:
        for name, c in top_channels:
            report.append(f"#{name} — {c} msgs")
    else:
        report.append("—")

    report.append("\n⚙️ Summary: steady engagement — H-Alliance Automation.")
    return "\n".join(report)

def post_to_slack(text):
    try:
        client.chat_postMessage(channel=channel_id, text=text)
        print("✅ Report sent to Slack.")
    except SlackApiError as e:
        print("Error sending message:", e.response.get('error'))

if __name__ == "__main__":
    text = generate_report()
    post_to_slack(text)
