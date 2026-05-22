from dolby_tool.compare import compare_files
from dolby_tool.tvlog import _parse_line


def test_parse_line_figalternate():
    line = (
        'FigAlternate(504) [Peak/Avg 30570719/24765202] [3840x1606] '
        '[dvh1.05.06,ec-3] [VideoRange PQ] [HDCP Type1] [FrameRate 23.976]'
    )
    out = _parse_line(line)
    assert out is not None
    assert out["kind"] == "hls_variant"
    assert out["peak_bps"] == 30570719
    assert out["height"] == 1606


def test_parse_line_codec_type():
    out = _parse_line('CodecType: dvh1 (HW decoder), DecodedPixelBuffer: &xv0, 3840 x 1600')
    assert out is not None
    assert out["kind"] == "codec_type"
    assert out["fourcc"] == "dvh1"


def test_compare_uses_custom_weights(monkeypatch):
    spec = {
        "path": "/tmp/a.mp4",
        "filename": "a.mp4",
        "video": {
            "dolby_vision": {"present": True, "profile": "8.1"},
            "fourcc": "dvh1",
            "hdr10_plus": True,
            "bit_rate_mbps": 80,
            "width": 3840,
            "height": 2160,
        },
        "audio": [{"atmos": True}],
        "subtitles": [1, 2, 3],
        "container": {"size_pretty": "1.0 GiB", "duration_pretty": "01:00:00"},
    }

    monkeypatch.setattr("dolby_tool.compare.inspect_file", lambda _p: spec)
    res = compare_files(["/tmp/a.mp4"], weights={"dv_present": 100, "subtitles": 0})
    assert res["weights"]["dv_present"] == 100.0
    assert res["weights"]["subtitles"] == 0.0
    assert res["scores"][0]["components"]["dv_present"] == 100.0
