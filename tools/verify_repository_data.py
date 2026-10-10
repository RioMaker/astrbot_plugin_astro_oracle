"""从本地 HEAD 克隆到任务临时目录，禁网验证接收端随附数据的实际星图输出。"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "repository-validation"
SCRIPT = r"""
import asyncio,json,sys
from datetime import datetime,timezone
from pathlib import Path
import httpx
from PIL import Image
import local_core
from local_core.bot_commands import ChartSettings,parse_request
from local_core.bot_service import ChartService
from local_core.bundled_resources import BUNDLE_DIR,resource_files
from local_core.resources import sha256_file
root=Path.cwd().resolve()
assert Path(local_core.__file__).resolve().parents[1]==root
assert BUNDLE_DIR==root/'assets/astronomy'
assert not (root/'data').exists()
requests=[]
async def blocked(self,request,*args,**kwargs):
    requests.append(str(request.url))
    raise AssertionError('Repository synchronization test forbids HTTP')
httpx.AsyncClient.send=blocked
cache=root/'data/plugin_data/astrbot_plugin_astro_oracle'
service=ChartService(cache)
async def render():
    try:
        png=await service.generate(parse_request('time 2026-10-10 20:30:00'),
            ChartSettings(),datetime(2026,10,10,tzinfo=timezone.utc))
        assert service.ready and service._sky.core.path.parent==cache
        Path(sys.argv[1]).write_bytes(png)
    finally:
        await service.close()
asyncio.run(render())
assert not requests
files=resource_files(BUNDLE_DIR)
assert len(files)==11
for name in files:
    assert sha256_file(cache/name)==sha256_file(BUNDLE_DIR/name)
with Image.open(sys.argv[1]) as image:
    assert image.size==(1760,1650)
print(json.dumps({'resource_file_count':len(files),'http_requests':requests,
    'resource_bytes':sum((BUNDLE_DIR/name).stat().st_size for name in files),
    'result':'Fresh Git checkout bootstrapped an empty framework cache and generated a real PNG'}))
"""


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    head = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    with tempfile.TemporaryDirectory(prefix="astro-git-", dir=OUTPUT) as temporary:
        checkout = (Path(temporary) / "checkout").resolve()
        assert checkout.is_relative_to(OUTPUT.resolve()) and checkout != ROOT
        subprocess.run(
            ["git", "clone", "--local", "--no-hardlinks", "--quiet", str(ROOT), str(checkout)],
            check=True,
            capture_output=True,
        )
        clone_head = subprocess.check_output(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True
        ).strip()
        assert clone_head == head
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env["PYTHONNOUSERSITE"] = "1"
        result = subprocess.run(
            [sys.executable, "-X", "utf8", "-c", SCRIPT, str(OUTPUT / "fresh-clone.png")],
            cwd=checkout,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        report = json.loads(result.stdout.strip().splitlines()[-1])
    report.update(commit=head, clone_mode="local, no hardlinks", scope="No remote AstrBot/QQ send")
    (OUTPUT / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("PASS: fresh Git clone, 11 public files, empty cache, HTTP disabled, real PNG.")
    print(OUTPUT / "fresh-clone.png")


if __name__ == "__main__":
    main()
