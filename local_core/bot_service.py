"""串行工作线程内准备公共资源、计算和绘图；查询资料仅存在内存中。"""

import asyncio
from concurrent.futures import ThreadPoolExecutor

from .bot_commands import resolve_place, resolve_time
from .engine import PlanetEngine
from .image_styles import render_style_png
from .resources import prepare_all
from .sky_chart import SkyChartEngine


class ChartService:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="astro-sky")
        self._sky = None
        self._closed = False
        self._close_future = None

    @property
    def ready(self):
        return self._sky is not None

    def _engine(self):
        if self._sky is None:
            asyncio.run(prepare_all(self.data_dir))
            core = PlanetEngine(self.data_dir)
            try:
                self._sky = SkyChartEngine(core)
            except BaseException:
                core.close()
                raise
        return self._sky

    def _generate(self, request, settings, now):
        sky = self._engine()
        site, zone, source = resolve_place(
            sky.places, request.place_text or settings.default_place, settings.coordinate_timezone
        )
        zone = request.timezone_override or zone
        moment, note = resolve_time(request, zone, settings.default_time, now)
        data = sky.compute(moment.isoformat(), site, zone, settings.magnitude_limit)
        data.update(time_note=note, timezone=zone, site_source=source)
        return render_style_png(data, settings, "observatory")

    async def generate(self, request, settings, now):
        if self._closed:
            raise RuntimeError("星图服务已停止，请重载插件。")
        return await asyncio.get_running_loop().run_in_executor(
            self._worker, self._generate, request, settings, now
        )

    def _close(self):
        try:
            if self._sky is not None:
                self._sky.core.close()
                self._sky = None
        finally:
            # 即使等待 close() 的协程被取消，工作线程完成清理后仍自行退出。
            self._worker.shutdown(wait=False, cancel_futures=True)

    async def close(self):
        if self._close_future is None:
            self._closed = True
            # 排在已提交计算之后关闭历表，避免取消协程时关闭仍在使用的内存映射。
            self._close_future = asyncio.get_running_loop().run_in_executor(
                self._worker, self._close
            )
        await asyncio.shield(self._close_future)
