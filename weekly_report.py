import os
import time
from datetime import datetime, timedelta, timezone
from collections import Counter
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
channel_id = os.environ["SLACK_CHANNEL_ID"]

def ts_days_ago(days=7):
    return str((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())

def list_channels():
    chans, cursor = [], None
    while True:
        resp = client.conversations_list(types="public_channel", limit=100, cursor=cursor)
        chans += [c for c in resp["channels"] if not c.get("is_archived")]
        cursor = resp.get("response_metadata", {}).get("next_cursor") or None
        if not cursor:
            break
    return chans

def channel_messages(ch_id, oldest):
    msgs, cursor = [], None
    while True:
        resp = client.conversations_history(channel=ch_id, oldest=oldest, limit=200, cursor=cursor)
        msgs += resp.get("messages", [])
        cursor = resp.get("response_metadata", {}).get("next_cursor") or None
        if not cursor:
            break
    return msgs

def users_map():
    users, cursor = {}, None
    while True:
        resp = client.users_list(limit=200, cursor=cursor)
        for m in resp["members"]:
            if not m.get("is_bot") and not m.get("deleted"):
                users[m["id"]] = m
        cursor = resp.get("response_metadata", {}).get("next_cursor") or None
        if not cursor:
            break
    return users

def generate_report():
    oldest = ts_days_ago(7)
    users = users_map()
    by_user = Counter()
    by_channel = Counter()

    for ch in list_channels():
        msgs = channel_messages(ch["id"], oldest)
        for m in msgs:
            u = m.get("user")
            if u in users:
                by_user[u] += 1
        by_channel[ch["name"]] += len(msgs)

    total_msgs = sum(by_channel.values())
    top_users = [(users[u]["profile"].get("real_name") or users[u]["name"], c)
                 for u, c in by_user.most_common(5)]
    top_channels = by_channel.most_common(4)

    week_range = f"{(datetime.now()-timedelta(days=7)).strftime('%b %d')}–{datetime.now().strftime('%b %d')}"
    report = [f"📅 *Weekly Slack Activity — Week of {week_range}*",
              f"\n💬 Total messages: {total_msgs}",
              f"👥 Active members: {len([u for u,c in by_user.items() if c>0])}"]

    report.append("\n🏆 *Top 5 Active Users*")
    for i, (name, c) in enumerate(top_users, 1):
        report.append(f"{i}️⃣ {name} — {c} msgs")

    report.append("\n📣 *Most Active Channels*")
    for name, c in top_channels:
        report.append(f"#{name} — {c} msgs")

    report.append("\n⚙️ Summary: steady engagement, auto-report from H-Alliance Automation.")
    return "\n".join(report)

def post_to_slack(text):
    try:
        client.chat_postMessage(channel=channel_id, text=text)
        print("✅ Report sent to Slack.")
    except SlackApiError as e:
        print("Error:", e.response["error"])

if __name__ == "__main__":
    text = generate_report()
    post_to_slack(text)
