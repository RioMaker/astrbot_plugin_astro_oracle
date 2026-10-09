"""本地 GeoNames 城市/乡镇搜索，不发送用户查询到外部服务。"""

import unicodedata

from .sky_resources import load_dataset


def normalize(text):
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(ch)
    )


class PlaceSearch:
    def __init__(self, directory, manifest):
        self.rows = load_dataset(directory, manifest, "cities")["rows"]
        self.keys = [normalize(",".join((row[1], row[2], row[3]))) for row in self.rows]

    def search(self, query):
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 80:
            raise ValueError("请输入 1–80 字的城市或乡镇名称。")
        key = normalize(query.strip())
        matches = []
        for row, index in zip(self.rows, self.keys):
            if key not in index:
                continue
            exact = key in [normalize(name) for name in [row[1], row[2], *row[3].split(",")]]
            matches.append((not exact, -row[8], row))
        matches.sort(key=lambda item: (item[0], item[1]))
        return [
            {
                "id": row[0],
                "name": row[1],
                "country": row[6],
                "latitude": row[4],
                "longitude": row[5],
                "timezone": row[7],
                "source": "GeoNames cities1000",
            }
            for _, _, row in matches[:10]
        ]
