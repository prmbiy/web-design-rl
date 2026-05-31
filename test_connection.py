import os
os.environ.pop("ANTHROPIC_BASE_URL", None)
os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)

from dotenv import load_dotenv
load_dotenv("/local/mnt/workspace/pbiyani/Projects/Proximal/web-design-rl/.env")

import anthropic
import httpx

client = anthropic.Anthropic(
    api_key=os.environ["ANTHROPIC_API_KEY"],
    base_url="https://api.anthropic.com",
    http_client=httpx.Client(verify=False),
)

msg = client.messages.create(
    model="claude-opus-4-7",
    max_tokens=50,
    messages=[{"role": "user", "content": "say hello world"}],
)
print("SUCCESS:", msg.content[0].text)
