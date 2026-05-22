from dolby_tool.compare import compare_files
from dolby_tool.tvlog import LogCapture, _parse_line


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


def test_qdh1_cloud_capture_is_recognized_but_not_confirmed_dv():
    lines = [
        "FILE_PLAYER HEVC enc=4 3840x1606",
        "HLS_VARIANT nullxnull",
        "CODEC_TYPE qdh1 (HW decoder)",
        "LUMA_CHROMA luma=10 chroma=1",
        "FILE_PLAYER HEVC enc=4 1918x802",
        "AUDIO_FORMAT qc+3 is decodable ch=16",
        "CODEC_TYPE qdh1 (HW decoder)",
    ]
    events = [_parse_line(line) for line in lines]
    assert all(event is not None for event in events)

    capture = LogCapture()
    capture.events = [event for event in events if event is not None]
    summary = capture.summarize()
    playback = summary["playback"]

    assert playback["source"] == "hls"
    assert playback["decoded_fourcc"] == "qdh1"
    assert playback["dolby_vision_active"] is None
    assert playback["dv_label"] == "Possibly DV / Apple private HDR path"
    assert "known hvc1 fallback" in playback["dv_diagnosis"]
    assert playback["file_player"]["encryption_scheme"] == 4
    assert playback["audio"]["format"] == "qc+3"
    assert playback["audio"]["channels"] == 16
    assert playback["audio"]["decodable"] is True
    assert playback["audio"]["is_atmos"] is False
    assert "unknown Dolby-like" in playback["audio"]["diagnosis"]
    assert playback["best_audio"]["format"] == "qc+3"
    assert playback["observed_audio"] == [{**playback["audio"], "count": 1}]


def test_tv_capture_keeps_current_best_and_observed_audio():
    lines = [
        "CODEC_TYPE qdh1 (HW decoder)",
        "AUDIO_FORMAT ec+3 is decodable ch=16",
        "AUDIO_FORMAT qaac is decodable ch=2",
        "AUDIO_FORMAT qaac is decodable ch=2",
    ]
    events = [_parse_line(line) for line in lines]
    assert all(event is not None for event in events)

    capture = LogCapture()
    capture.events = [event for event in events if event is not None]
    playback = capture.summarize()["playback"]

    assert playback["audio"]["format"] == "qaac"
    assert playback["audio"]["channels"] == 2
    assert playback["best_audio"]["format"] == "ec+3"
    assert playback["best_audio"]["channels"] == 16
    assert playback["observed_audio"] == [
        {
            "format": "ec+3",
            "channels": 16,
            "sample_rate": None,
            "spatialization": None,
            "spatialization_eligible": None,
            "decodable": True,
            "is_atmos": False,
            "count": 1,
        },
        {
            "format": "qaac",
            "channels": 2,
            "sample_rate": None,
            "spatialization": None,
            "spatialization_eligible": None,
            "decodable": True,
            "is_atmos": False,
            "count": 2,
        },
    ]


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
