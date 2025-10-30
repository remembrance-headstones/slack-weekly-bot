import os
import json
from datetime import datetime, timedelta, timezone
from collections import Counter
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
channel_id = os.environ.get("SLACK_CHANNEL_ID", "D09KW4FTQ1E")

TREND_FILE = "trend.json"

def ts_days_ago(days=7):
    return str((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())

def list_channels():
    chans, cursor = [], None
    while True:
        resp = client.conversations_list(types="public_channel", limit=200, cursor=cursor)
        chans += [
            c for c in resp.get("channels", [])
            if not c.get("is_archived") and c.get("is_member")
        ]
        cursor = resp.get("response_metadata", {}).get("next_cursor") or None
        if not cursor:
            break
    return chans

def channel_messages(ch_id, oldest):
    msgs, cursor = [], None
    try:
        while True:
            resp = client.conversations_history(channel=ch_id, oldest=oldest, limit=200, cursor=cursor)
            msgs += resp.get("messages", [])
            cursor = resp.get("response_metadata", {}).get("next_cursor") or None
            if not cursor:
                break
    except SlackApiError as e:
        print(f"Skip {ch_id}:", e.response.get("error"))
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

def load_trend():
    if os.path.exists(TREND_FILE):
        with open(TREND_FILE, "r") as f:
            return json.load(f)
    return {"previous_msgs": 0, "active_users": [], "weeks": []}

def save_trend(data):
    with open(TREND_FILE, "w") as f:
        json.dump(data, f)

def generate_report():
    oldest = ts_days_ago(7)
    users = users_map()
    by_user = Counter()
    by_channel = Counter()

    for ch in list_channels():
        msgs = channel_messages(ch["id"], oldest)
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
    active_users = [u for u, c in by_user.items() if c > 0]
    quiet_users = [users[u]["profile"].get("real_name") for u, c in by_user.items() if c < 3]

    # trend data
    trend = load_trend()
    prev_msgs = trend.get("previous_msgs", 0)
    prev_users = set(trend.get("active_users", []))
    weeks = trend.get("weeks", [])
    growth = (total_msgs - prev_msgs) / prev_msgs * 100 if prev_msgs else 0
    new_active = [users[u]["profile"].get("real_name") for u in active_users if u not in prev_users]

    # update trend
    trend["previous_msgs"] = total_msgs
    trend["active_users"] = active_users
    weeks.append(total_msgs)
    if len(weeks) > 4:
        weeks = weeks[-4:]
    trend["weeks"] = weeks
    save_trend(trend)

    # top users and channels
    top_users = [
        (users[u]["profile"].get("real_name") or users[u].get("name") or u, c)
        for u, c in by_user.most_common(5)
    ]
    top_channels = by_channel.most_common(4)

    week_range = f"{(datetime.now()-timedelta(days=7)).strftime('%b %d')}–{datetime.now().strftime('%b %d')}"
    report = [f"📬 *H-Alliance Weekly Summary*",
              f"📅 Week of {week_range}",
              f"\n💬 Total messages: {total_msgs}",
              f"👥 Active members: {len(active_users)}",
              f"📈 Change vs last week: {growth:+.1f}%" if prev_msgs else "📈 First data week"]

    report.append("\n🏆 *Top 5 Active Users*")
    for i, (name, c) in enumerate(top_users, 1):
        report.append(f"{i}️⃣ {name} — {c} msgs")

    report.append("\n📣 *Most Active Channels*")
    for name, c in top_channels:
        report.append(f"#{name} — {c} msgs")

    if quiet_users:
        report.append("\n🔕 *Quiet Users*:\n" + ", ".join(quiet_users))
    if new_active:
        report.append(f"\n🌱 *Emerging Voices*: {len(new_active)} new active users this week")

    # message trend (last 4 weeks)
    if len(weeks) > 1:
        report.append("\n📊 *Message Trend (last 4 weeks)*")
        for w in weeks[-4:]:
            bar = "▇" * int(w / max(weeks) * 20)
            report.append(f"{bar} {w} msgs")

    report.append("\n⚙️ Summary: steady engagement — H-Alliance Automation.")
    return "\n".join(report)

def post_to_slack(text):
    try:
        client.chat_postMessage(channel=channel_id, text=text)
        print("✅ Report sent to Slack (DM).")
    except SlackApiError as e:
        print("Error:", e.response.get("error"))

if __name__ == "__main__":
    text = generate_report()
    post_to_slack(text)
