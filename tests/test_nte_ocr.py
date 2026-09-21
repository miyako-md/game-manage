"""nte_ocr 辅助命令测试。

RapidOCR 为可选依赖：真 OCR 调用不进测试（标注可选依赖）；
"依赖缺失"用例通过 monkeypatch sys.modules 模拟（venv 里可能已装）。
"""
import sys

import httpx
import pytest
import respx

from game_assistant import nte_ocr

def test_parse_args_news_page_and_inputs():
    ns = nte_ocr.parse_args().parse_args(
        ["--news-page", "https://p.example/news/1", "https://i.example/a.jpg",
         "D:/截图/长图.png"])
    assert ns.news_page == "https://p.example/news/1"
    assert ns.inputs == ["https://i.example/a.jpg", "D:/截图/长图.png"]


def test_parse_args_inputs_only():
    ns = nte_ocr.parse_args().parse_args(["a.png", "b.jpeg"])
    assert ns.news_page is None
    assert ns.inputs == ["a.png", "b.jpeg"]


def test_parse_args_no_args_allowed():
    # 空参数不抛 SystemExit：main 里自行打印帮助并返回 2
    ns = nte_ocr.parse_args().parse_args([])
    assert ns.news_page is None and ns.inputs == []


def test_extract_image_urls_src_and_data_src():
    html = ('<img src="https://a.example/x.PNG">'
            '<img data-src="https://a.example/y.jpg?x=1">'
            '<img src="/rel/p.webp">'
            '<img src="https://a.example/skip.gif">'
            '<script src="https://a.example/app.js"></script>')
    urls = nte_ocr.extract_image_urls(
        html, base_url="https://a.example/news/1")
    # png/jpg/jpeg/webp 大小写不敏感、带查询串保留、相对 URL 补全；gif/js 排除
    assert urls == ["https://a.example/x.PNG", "https://a.example/y.jpg?x=1",
                    "https://a.example/rel/p.webp"]


def test_extract_image_urls_dedupes_preserving_order():
    html = '<img src="b.png"><img src="a.png"><img src="b.png">'
    assert nte_ocr.extract_image_urls(html) == ["b.png", "a.png"]


@respx.mock
def test_fetch_news_page_images():
    route = respx.get("https://pvp.example.com/nte/news/123.shtml").mock(
        return_value=httpx.Response(200, text=(
            '<div><img src="https://img.example.com/a.jpg"></div>'
            '<img data-src="b.webp">')))
    urls = nte_ocr.fetch_news_page_images(
        "https://pvp.example.com/nte/news/123.shtml")
    assert urls == ["https://img.example.com/a.jpg",
                    "https://pvp.example.com/nte/news/b.webp"]
    # 抓页面带浏览器 UA（部分站点按 UA 拦截）
    assert route.calls.last.request.headers["user-agent"].startswith(
        "Mozilla/5.0")


@respx.mock
def test_main_news_page_mode_prints_urls(capsys):
    respx.get("https://p.example/n").mock(return_value=httpx.Response(
        200, text='<img src="/i/a.jpg">'))
    assert nte_ocr.main(["--news-page", "https://p.example/n"]) == 0
    assert "https://p.example/i/a.jpg" in capsys.readouterr().out


def test_main_missing_rapidocr_friendly_error(monkeypatch, capsys):
    # sys.modules 里置 None → import 抛 ImportError（模拟未安装，venv 可能已装）
    monkeypatch.setitem(sys.modules, "rapidocr_onnxruntime", None)
    rc = nte_ocr.main(["some.png"])
    assert rc == 1
    err = capsys.readouterr().err
    assert 'pip install -e ".[ocr]"' in err


def test_main_no_args_prints_help(capsys):
    assert nte_ocr.main([]) == 2
    out = capsys.readouterr().out
    assert "用法" in out or "news-page" in out


def test_load_ocr_engine_unavailable(monkeypatch):
    # sys.modules 置 None 模拟未安装（venv 里可能已装）→ OcrUnavailableError
    monkeypatch.setitem(sys.modules, "rapidocr_onnxruntime", None)
    with pytest.raises(nte_ocr.OcrUnavailableError) as ei:
        nte_ocr.load_ocr_engine()
    assert 'pip install -e ".[ocr]"' in str(ei.value)


@pytest.mark.parametrize("dependency", ["cv2", "numpy"])
def test_load_image_missing_dependency_has_install_hint(monkeypatch, dependency):
    monkeypatch.setitem(sys.modules, dependency, None)
    with pytest.raises(nte_ocr.OcrUnavailableError, match=r"\[ocr\]"):
        nte_ocr.load_image("some.png")


def test_load_image_local_non_ascii_path(tmp_path):
    # Windows 中文路径：cv2.imread 会失败（实测教训），须走 np.fromfile+imdecode
    import cv2
    import numpy as np

    ok, buf = cv2.imencode(".png", np.zeros((4, 4, 3), dtype=np.uint8))
    assert ok
    p = tmp_path / "长图测试.png"
    p.write_bytes(buf.tobytes())
    img = nte_ocr.load_image(str(p))
    assert img.shape == (4, 4, 3)


@respx.mock
def test_load_image_download_with_ua():
    import cv2
    import numpy as np

    ok, buf = cv2.imencode(
        ".jpg", np.arange(18, dtype=np.uint8).reshape(3, 2, 3))
    assert ok
    route = respx.get("https://img.example/a.jpg").mock(
        return_value=httpx.Response(200, content=buf.tobytes()))
    img = nte_ocr.load_image("https://img.example/a.jpg")
    assert img.shape[0:2] == (3, 2)
    assert route.calls.last.request.headers["user-agent"].startswith(
        "Mozilla/5.0")


def test_load_image_bad_content_raises(tmp_path):
    p = tmp_path / "notimage.png"
    p.write_bytes(b"definitely not an image")
    try:
        nte_ocr.load_image(str(p))
    except ValueError as e:
        assert "解码失败" in str(e) or "读取" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_ocr_lines_sorts_by_y_with_fake_engine():
    # 真 RapidOCR 不进测试：用假引擎复刻返回形状 [box(4 点), text, score]
    class FakeEngine:
        def __call__(self, image):
            result = [
                [[[0, 100], [10, 100], [10, 110], [0, 110]], "第二行", "0.90"],
                [[[0, 10], [10, 10], [10, 20], [0, 20]], "第一行", "0.80"],
            ]
            return result, None

    lines = nte_ocr.ocr_lines(FakeEngine(), object())
    assert [t for t, _s in lines] == ["第一行", "第二行"]
    assert lines[0][1] == 0.8  # 置信度转 float
