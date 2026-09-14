import json
import shutil
import subprocess
import pytest
from server.course_playback import join_page, read_page, playback_signature


def test_join_real_mp4_and_reuse(tmp_path, monkeypatch):
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        pytest.skip('ffmpeg unavailable')
    monkeypatch.setenv('FFMPEG_BIN', ffmpeg)
    clip = tmp_path/'input.mp4'
    subprocess.run([ffmpeg,'-v','error','-f','lavfi','-i','color=c=green:s=160x90:r=25',
                    '-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','0.6',
                    '-c:v','libx264','-c:a','aac','-movflags','+faststart',str(clip)],check=True)
    data=clip.read_bytes()
    info=join_page(tmp_path,'identity',0,[('你好。',data),('再看这里。',data)])
    output=tmp_path/'course-playback/identity/0.mp4'
    content=output.read_bytes()
    assert content.index(b'moov') < content.index(b'mdat'), 'metadata precedes media for fast start'
    assert len(info['segments']) == 2 and info['segments'][1]['offset'] == 3
    assert 1.1 < info['duration'] < 1.4
    assert read_page(tmp_path,'identity',0) == info
    monkeypatch.setenv('FFMPEG_BIN','/does/not/exist')
    assert join_page(tmp_path,'identity',0,[]) == info, 'completed video reuses without encoding'
    output.write_bytes(b'truncated')
    assert read_page(tmp_path,'identity',0) is None


def test_signature_tracks_content_and_materials(monkeypatch):
    course={'id':'c','slides':[{'narration':'你好'}]}
    teacher={'voice_profile_id':'v','avatar_asset_id':'a'}
    key=playback_signature(course,teacher,'image1')
    assert key != playback_signature(course,teacher,'image2')
    assert key != playback_signature(course,{**teacher,'voice_profile_id':'new'},'image1')
    assert key != playback_signature({**course,'slides':[{'narration':'再见'}]},teacher,'image1')
    monkeypatch.setenv('MEDIA_CACHE_VERSION','new')
    assert key != playback_signature(course,teacher,'image1')
