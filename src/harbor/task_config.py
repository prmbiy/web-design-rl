def render_task_toml(task_id: str, task_name: str, page_count: int) -> str:
    return f"""schema_version = "1.1"

[task]
name = "web-design-rl/{task_id}"
description = "{page_count}-page website design replication ({task_name})"
keywords = ["design-to-code", "web", "html", "css", "visual-replication"]

[metadata]
task_id = "{task_id}"
category = "design-to-code"
framework = "html_css"
page_count = {page_count}
generator = "web-design-rl"

[agent]
timeout_sec = 1800.0
user = "agent"

[verifier]
timeout_sec = 600.0
user = "root"

[environment]
build_timeout_sec = 1200.0
os = "linux"
cpus = 2
memory_mb = 4096
allow_internet = true
"""
