# 第三方数据与算法说明

本地原型的科学结果由真实数据与明确计算模型生成。下载资源保存在被忽略的 `data/`，代码仓库不包含原始星表、地名库或历表大文件。

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
