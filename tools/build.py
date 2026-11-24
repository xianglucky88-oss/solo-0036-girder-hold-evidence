from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    sources = sorted((ROOT / "girder").glob("*.py")) + sorted((ROOT / "tools").glob("*.py"))
    for source in sources:
        compile(source.read_bytes(), str(source), "exec")
    assets = [ROOT / "web/index.html", *sorted((ROOT / "web").glob("*.js")), *sorted((ROOT / "web/css").glob("*.css"))]
    for asset in assets:
        if not asset.read_text(encoding="utf-8").strip():
            raise SystemExit(f"页面资源为空：{asset.relative_to(ROOT)}")
    print(f"编译 {len(sources)} 个 Python 源文件，读取 {len(assets)} 个原生页面资源")


if __name__ == "__main__":
    main()
