import asyncio
from server.media_cache import MediaCache


def test_persistent_cache_and_identity_changes(tmp_path):
    async def run():
        calls = 0
        async def produce():
            nonlocal calls
            calls += 1
            await asyncio.sleep(.01)
            return b'video-bytes', 'video/mp4'
        cache = MediaCache(tmp_path)
        values = await asyncio.gather(*(cache.get({'voice':'a','text':'你好'},produce) for _ in range(3)))
        assert calls == 1
        assert sum(not value[2] for value in values) == 1
        assert (await MediaCache(tmp_path).get({'voice':'a','text':'你好'},produce))[2]
        await cache.get({'voice':'b','text':'你好'},produce)
        assert calls == 2
        for path in (tmp_path/'speech-cache').glob('*.bin'):
            path.write_bytes(b'corrupt')
        assert not (await cache.get({'voice':'a','text':'你好'},produce))[2]
        assert calls == 3
    asyncio.run(run())
