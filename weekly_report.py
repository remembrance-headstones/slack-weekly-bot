import os
from slack_sdk import WebClient

client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
channel = os.environ["SLACK_CHANNEL_ID"]

client.chat_postMessage(
    channel=channel,
    text="✅ Test message from H-Alliance Automation — system online."
)
