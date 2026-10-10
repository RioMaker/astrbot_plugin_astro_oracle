# 随仓库保存的公共天文资源

本目录的 11 个数据文件已下载、校验并纳入本插件的独立 Git 仓库，供开发机同步及运行端离线使用。

- `de440s.bsp`、`ephemeris.json`：NASA/JPL DE440s，文件 SHA-256、实际来源与覆盖范围见来源记录。
- `sky/hip_main.dat`、`hipparcos-readme.txt`：ESA Hipparcos 1997 / CDS I/239 原始资料。
- `sky/modern_st.json`、`modern_st-description.md`：Stellarium Modern (Sky & Telescope)，CC BY-SA 2.0，作者 Paul Krizak、Jonathan E. Piskor、G. Zotti。
- `sky/cities1000.zip`、`geonames-readme.txt`：GeoNames 地点数据与说明，CC BY 4.0。
- `sky/stars.json.gz`、`cities.json.gz`、`manifest.json`：编译数据、来源与校验值；原始及编译数据一并保留。

完整归属与许可见 [第三方资料说明](../../THIRD_PARTY_NOTICES.md)。`.gitattributes` 对本目录关闭文本换行转换，原始字节与 SHA-256 在 Windows/Linux 同步后保持一致。

运行时先校验随附快照，再将上述明确列出的公共文件准备到框架数据目录；同样的文件直接复用，缺失或不匹配的公共文件按该快照同步。框架目录的其他文件不参与同步。用户查询和生成结果仍不自动保存。
