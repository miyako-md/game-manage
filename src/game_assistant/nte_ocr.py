"""异环活动长图 OCR 辅助命令行（可选依赖 RapidOCR，真调用不进自动化测试）。

背景：异环官网前瞻/回顾页的活动起止日期在长图里，HTML 无结构化日期；
长图 OCR 自动解析不可靠（实测 11 行日期仅 1 行全对），故本命令只做
"按行提取文本 + 置信度"，供人工比对长图后抄写进 config.toml 的
[[nte_events]]（每版本填一次），解析入库走可靠的手填主路径。

用法：
  # 列出新闻页全部图片 URL（png/jpg/jpeg/webp，src/data-src）
  python -m game_assistant.nte_ocr --news-page <新闻页URL>

  # 对一个或多个图片（URL 或本地路径）OCR，按 y 坐标排序打印行文本+置信度
  python -m game_assistant.nte_ocr <图片URL或本地路径> [<图片URL或本地路径> ...]

RapidOCR 为可选依赖：未安装时提示 `pip install rapidocr-onnxruntime`
并以退出码 1 退出。
"""
import argparse
import re
import sys
from urllib.parse import urljoin

import httpx

UA = "Mozilla/5.0"

# src/data-src 指向的图片（png/jpg/jpeg/webp，大小写不敏感，保留查询串）
IMAGE_URL_RE = re.compile(
    r"""(?:src|data-src)\s*=\s*["']([^"']+\.(?:png|jpe?g|webp)(?:\?[^"']*)?)["']""",
    re.IGNORECASE)

TIMEOUT_PAGE = 30.0
TIMEOUT_IMAGE = 60.0


def extract_image_urls(html: str, base_url: str | None = None) -> list[str]:
    """HTML → 图片 URL 列表（src/data-src，png/jpg/jpeg/webp）。

    顺序保留去重；base_url 给定时相对 URL 经 urljoin 补全。
    """
    urls: list[str] = []
    seen: set[str] = set()
    for m in IMAGE_URL_RE.finditer(html or ""):
        u = urljoin(base_url, m.group(1).strip()) if base_url \
            else m.group(1).strip()
        if u not in seen:
            seen.add(u)
            urls.append(u)
    return urls


def fetch_news_page_images(url: str) -> list[str]:
    """抓新闻页 HTML → 页面内全部图片 URL（带浏览器 UA，跟随跳转）。"""
    resp = httpx.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT_PAGE,
                     follow_redirects=True)
    resp.raise_for_status()
    return extract_image_urls(resp.text, base_url=str(resp.url))


class OcrUnavailableError(RuntimeError):
    """RapidOCR（可选依赖）未安装。"""


def load_ocr_engine():
    try:
        from rapidocr_onnxruntime import RapidOCR  # 可选依赖，刻意懒加载
    except ImportError as e:  # pragma: no cover - venv 已装时走不到
        raise OcrUnavailableError(
            "未安装 RapidOCR（可选依赖）。请先执行："
            "pip install rapidocr-onnxruntime") from e
    return RapidOCR()


def load_image(source: str):
    """图片 URL 下载 / 本地路径读取 → BGR ndarray（cv2.imdecode）。

    本地路径必须走 np.fromfile + cv2.imdecode：Windows 中文路径下
    cv2.imread 会失败（实测教训）。
    """
    import cv2
    import numpy as np

    if source.startswith(("http://", "https://")):
        resp = httpx.get(source, headers={"User-Agent": UA},
                         timeout=TIMEOUT_IMAGE, follow_redirects=True)
        resp.raise_for_status()
        raw = np.frombuffer(resp.content, dtype=np.uint8)
    else:
        raw = np.fromfile(source, dtype=np.uint8)
    img = cv2.imdecode(raw, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"图片解码失败（非图片或已损坏）：{source}")
    return img


def ocr_lines(engine, image) -> list[tuple[str, float]]:
    """OCR → [(行文本, 置信度)]，按检测框 y 坐标（自上而下）排序。

    RapidOCR 返回形状：[[box(4 点), text, score], ...]（可能为 None）。
    """
    result = engine(image)
    if isinstance(result, tuple):
        result = result[0]
    rows = []
    for item in result or []:
        box, text, score = item[0], item[1], float(item[2])
        y = min(p[1] for p in box)
        rows.append((y, text, score))
    rows.sort(key=lambda r: r[0])
    return [(text, score) for _y, text, score in rows]


def parse_args() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m game_assistant.nte_ocr",
        description="异环活动长图 OCR 辅助：按行提取文本供人工比对抄写"
                    "（自动解析不可靠，以人眼比对长图为准）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：\n"
               "  python -m game_assistant.nte_ocr --news-page"
               " https://pvp.wanmei.com/nte/news/xxxx.shtml\n"
               "  python -m game_assistant.nte_ocr"
               " https://.../preview.jpg D:\\长图.png\n")
    parser.add_argument("--news-page", metavar="URL",
                        help="抓该新闻页 HTML 并列出全部图片 URL")
    parser.add_argument("inputs", nargs="*", metavar="图片",
                        help="图片 URL 或本地路径（可多个），OCR 后按行输出")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = parse_args()
    args = parser.parse_args(argv)
    if not args.news_page and not args.inputs:
        parser.print_help()
        return 2

    if args.news_page:
        try:
            urls = fetch_news_page_images(args.news_page)
        except Exception as e:
            print(f"新闻页抓取失败：{e}", file=sys.stderr)
            return 1
        if not urls:
            print("该页面未找到图片（png/jpg/jpeg/webp）。")
        for u in urls:
            print(u)

    if not args.inputs:
        return 0

    try:
        engine = load_ocr_engine()
    except OcrUnavailableError as e:
        print(str(e), file=sys.stderr)
        return 1

    failed = 0
    for src in args.inputs:
        try:
            image = load_image(src)
        except Exception as e:
            print(f"[跳过] {src}：{e}", file=sys.stderr)
            failed += 1
            continue
        print(f"== {src} ==")
        for text, score in ocr_lines(engine, image):
            print(f"{score:.2f}  {text}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
