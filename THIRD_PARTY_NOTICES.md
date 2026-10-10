# 第三方数据与算法说明

科学结果由真实数据与明确计算模型生成。用户已授权将原始及编译公共资源纳入本插件的本地 Git，固定快照位于 `assets/astronomy/`。本地调试缓存仍在被忽略的 `data/`，AstrBot 缓存仍在框架插件数据目录；两处缓存从随附快照准备。原始来源、作者、许可与 SHA-256 保留在快照中。

## NASA/JPL DE440s

行星历表来自 [NAIF 官方文件](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440s.bsp)。来源与实际 SHA-256 记录于 `data/ephemeris.json`。使用时注明 NASA Jet Propulsion Laboratory，并参考 [JPL 历表说明](https://rhodesmill.org/skyfield/planets.html)。

## Hipparcos 星表

ESA 1997，《The Hipparcos and Tycho Catalogues》，ESA SP-1200，CDS 编号 I/239。原始数据来自 [CDS hip_main.dat](https://cdsarc.cds.unistra.fr/ftp/cats/I/239/hip_main.dat)，字段说明见 [ReadMe](https://cdsarc.cds.unistra.fr/ftp/cats/I/239/ReadMe)。资源未重新标为本项目自有观测数据。

## Stellarium Sky & Telescope 图形与通用星名

来源：[Stellarium modern_st/index.json](https://github.com/Stellarium/stellarium/blob/master/skycultures/modern_st/index.json)，[原始作者与许可说明](https://github.com/Stellarium/stellarium/blob/master/skycultures/modern_st/description.md)。

作者为 Paul Krizak、Jonathan E. Piskor，G. Zotti 扩展。该星文化的星座图形与通用星名采用 [CC BY-SA 2.0](https://creativecommons.org/licenses/by-sa/2.0/)。本项目按真实观测方向对线段进行投影、地平线裁剪，并采用部分中文常用展示别名，属于显示适配。

星座数据和对应图形改编遵循该许可；界面与 PNG 保留来源及许可提示。对外分享这部分改编图形时保留署名、来源与同许可条件。本条不自动为本项目全部代码指定许可证。

## GeoNames

本地地点搜索使用 [GeoNames cities1000.zip](https://download.geonames.org/export/dump/cities1000.zip)，字段说明与数据许可见 [GeoNames ReadMe](https://download.geonames.org/export/dump/readme.txt)。该数据采用 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)，感谢 GeoNames 社区。结果为城市/乡镇中心，允许用户校正坐标；未使用外部在线搜索传输用户出生地查询。

## 光度模型与计算库

Skyfield 使用 Mallama & Hilton 2018，[Computing Apparent Planetary Magnitudes for The Astronomical Almanac](https://arxiv.org/abs/1808.01973) 的 V 波段光度模型。星等为估计值，模型限制按实际返回值与说明保留。Skyfield、jplephem、NumPy 和 httpx 通过依赖安装使用，相关库许可由各自分发包提供。
## 插件图片渲染

- **Pillow**（兼容范围 `>=11.3.0,<13`）：HPND / PIL Software License，通过依赖安装使用。保留 AstrBot 核心允许的已安装版本，不强制降级。来源 <https://github.com/python-pillow/Pillow>。
- **AstroSans.otf**：Noto Sans CJK SC Regular 的裁剪、重命名版本，采用 SIL OFL 1.1，原版权保留在字体元数据中。许可见 `assets/fonts/LICENSE.txt`，官方来源与原始/输出 SHA-256 见 `assets/fonts/provenance.json`。字体包含常用中日韩文字、拉丁文字与显示标点，可在无系统中文字体的环境使用。来源 <https://github.com/notofonts/noto-cjk>。构建脚本 `tools/build_font.py` 需要 fontTools 4.59.2（MIT），运行插件不需要该工具。
- 图片中的星座图形沿用本文已列明的 Stellarium Sky & Telescope 数据许可 CC BY-SA 2.0，保留作者、来源与许可链接。
