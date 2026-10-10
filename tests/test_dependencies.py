from pathlib import Path

from packaging.requirements import Requirement


def test_runtime_accepts_astrbot_core_pillow_12_3_without_downgrade():
    path = Path(__file__).resolve().parents[1] / "requirements.txt"
    requirements = [
        Requirement(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    pillow = next(req for req in requirements if req.name.casefold() == "pillow")
    # 用户实际 AstrBot 4.28.1 的受保护核心版本；旧的 ==11.3.0 会使本检查失败。
    assert "12.3.0" in pillow.specifier
