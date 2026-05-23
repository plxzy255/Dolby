from urllib.error import HTTPError
from urllib.request import Request, urlopen

from dolby_tool.local_hls import playlist_url, prepare_hls_from_movpkg, running_hls_server


def test_hls_server_supports_byte_ranges(tmp_path):
    (tmp_path / "master.m3u8").write_text("#EXTM3U\nsegment.m4s\n", encoding="utf-8")
    (tmp_path / "segment.m4s").write_bytes(b"0123456789")

    with running_hls_server(tmp_path, port=0, quiet=True) as server:
        url = playlist_url(server, "segment.m4s")
        request = Request(url, headers={"Range": "bytes=2-5"})
        with urlopen(request, timeout=5) as response:
            body = response.read()

    assert response.status == 206
    assert response.headers["Content-Range"] == "bytes 2-5/10"
    assert response.headers["Accept-Ranges"] == "bytes"
    assert body == b"2345"


def test_hls_server_supports_suffix_byte_ranges(tmp_path):
    (tmp_path / "segment.m4s").write_bytes(b"0123456789")

    with running_hls_server(tmp_path, port=0, quiet=True) as server:
        url = playlist_url(server, "segment.m4s")
        request = Request(url, headers={"Range": "bytes=-3"})
        with urlopen(request, timeout=5) as response:
            body = response.read()

    assert response.status == 206
    assert response.headers["Content-Range"] == "bytes 7-9/10"
    assert body == b"789"


def test_hls_server_rejects_unsatisfiable_ranges(tmp_path):
    (tmp_path / "segment.m4s").write_bytes(b"0123456789")

    with running_hls_server(tmp_path, port=0, quiet=True) as server:
        url = playlist_url(server, "segment.m4s")
        request = Request(url, headers={"Range": "bytes=99-120"})
        try:
            urlopen(request, timeout=5)
        except HTTPError as error:
            status = error.code
            content_range = error.headers["Content-Range"]
        else:
            raise AssertionError("expected HTTP 416")

    assert status == 416
    assert content_range == "bytes */10"


def test_prepare_hls_from_movpkg_flattens_persisted_streams(tmp_path):
    movpkg = tmp_path / "Test.movpkg"
    video_dir = movpkg / "0-video"
    audio_dir = movpkg / "1-audio"
    data_dir = movpkg / "Data"
    video_dir.mkdir(parents=True)
    audio_dir.mkdir(parents=True)
    data_dir.mkdir()
    (movpkg / "boot.xml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<HLSMoviePackage xmlns="http://apple.com/IMG/Schemas/HLSMoviePackage">
  <Streams>
    <Stream ID="0-video" NetworkURL="http://127.0.0.1:8765/video.m3u8" Path="0-video"><Complete>YES</Complete></Stream>
    <Stream ID="1-audio" NetworkURL="http://127.0.0.1:8765/audio.m3u8" Path="1-audio"><Complete>YES</Complete></Stream>
  </Streams>
  <DataItems Directory="Data">
    <DataItem><DataPath>master-source.m3u8</DataPath><Role>Master</Role></DataItem>
  </DataItems>
</HLSMoviePackage>
""",
        encoding="utf-8",
    )
    (data_dir / "master-source.m3u8").write_text(
        '#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1,AUDIO="atmos"\nvideo.m3u8\n\x00',
        encoding="utf-8",
    )
    _write_stream_info(video_dir, "video-source.m3u8", "video_seg.m4s", b"vinit", [b"v0", b"v1"])
    _write_stream_info(audio_dir, "audio-source.m3u8", "audio_seg.m4s", b"ainit", [b"a0", b"a1"])

    output = tmp_path / "out"
    summary = prepare_hls_from_movpkg(movpkg, output)

    assert (output / "master.m3u8").read_text(encoding="utf-8").endswith("video.m3u8\n")
    assert (output / "video.m3u8").read_text(encoding="utf-8").count("video_seg.m4s") == 3
    assert (output / "audio.m3u8").read_text(encoding="utf-8").count("audio_seg.m4s") == 3
    assert (output / "video_seg.m4s").read_bytes() == b"vinitv0v1"
    assert (output / "audio_seg.m4s").read_bytes() == b"ainita0a1"
    assert summary["master_playlist"] == "master.m3u8"
    assert len(summary["streams"]) == 2


def _write_stream_info(
    stream_dir,
    playlist_name: str,
    segment_name: str,
    init: bytes,
    fragments: list[bytes],
) -> None:
    (stream_dir / "init.initfrag").write_bytes(init)
    offset = len(init)
    segment_xml = []
    playlist_lines = [
        "#EXTM3U",
        f'#EXT-X-MAP:URI="{segment_name}",BYTERANGE="{len(init)}@0"',
    ]
    for index, data in enumerate(fragments):
        path = f"{index}.frag"
        (stream_dir / path).write_bytes(data)
        segment_xml.append(
            f'<SEG Dur="1.0" Len="{len(data)}" Off="{offset}" PATH="{path}" SeqNum="{index}" />'
        )
        playlist_lines.extend(
            [
                "#EXTINF:1.0,",
                f"#EXT-X-BYTERANGE:{len(data)}@{offset}",
                segment_name,
            ]
        )
        offset += len(data)
    (stream_dir / playlist_name).write_text("\n".join(playlist_lines) + "\n", encoding="utf-8")
    (stream_dir / "StreamInfoBoot.xml").write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<StreamInfo xmlns="http://apple.com/IMG/Schemas/HLSPersistentStreamInfo">
  <Complete>YES</Complete>
  <MediaPlaylist><PathToLocalCopy>{playlist_name}</PathToLocalCopy></MediaPlaylist>
  <MediaInitializationSegments>
    <ISEG Len="{len(init)}" Off="0" PATH="init.initfrag" SeqNum="0" />
  </MediaInitializationSegments>
  <MediaSegments>
    {''.join(segment_xml)}
  </MediaSegments>
  <MediaBytesStored>{offset}</MediaBytesStored>
</StreamInfo>
""",
        encoding="utf-8",
    )
