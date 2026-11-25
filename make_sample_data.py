"""
샘플(가상) 데이터 생성 스크립트
--------------------------------
실제 공공데이터를 받기 전에 대시보드를 바로 실행해 볼 수 있도록
'형식만 실제와 같은' 가상 데이터를 만듭니다.

※ 주의: 지역 이름·좌표·인구·응급실 위치는 모두 가상입니다.
   보고서에 쓸 최종 결과는 collect_er.py, prepare_regions.py로
   실제 데이터를 만든 뒤 다시 실행해서 얻어야 합니다.

실행:  python make_sample_data.py
결과:  data/sample/regions.csv, data/sample/er.csv
"""
import os
import numpy as np
import pandas as pd

rng = np.random.default_rng(42)

# 시도별 설정 (인구·고령비율은 대략적인 규모만 맞춘 값)
# hubs: (위도, 경도, 가중치) - 도시가 모여 있는 중심점
# box : 농어촌 지역을 흩뿌릴 범위 (lat_min, lat_max, lon_min, lon_max)
SIDO = {
    "서울특별시": dict(pop=935, old=0.19, n=25, rural=0, spread=0.06,
                   hubs=[(37.55, 126.99, 1)], box=None, er=(3, 22, 25)),
    "부산광역시": dict(pop=328, old=0.23, n=16, rural=0, spread=0.07,
                   hubs=[(35.17, 129.07, 1)], box=None, er=(1, 8, 14)),
    "대구광역시": dict(pop=236, old=0.20, n=9, rural=1, spread=0.07,
                   hubs=[(35.87, 128.60, 1)], box=(35.70, 36.05, 128.35, 128.75), er=(1, 6, 8)),
    "인천광역시": dict(pop=300, old=0.17, n=10, rural=2, spread=0.07,
                   hubs=[(37.46, 126.70, 1)], box=(37.20, 37.75, 126.10, 126.55), er=(2, 8, 10)),
    "광주광역시": dict(pop=141, old=0.17, n=5, rural=0, spread=0.05,
                   hubs=[(35.16, 126.85, 1)], box=None, er=(1, 4, 6)),
    "대전광역시": dict(pop=144, old=0.17, n=5, rural=0, spread=0.05,
                   hubs=[(36.35, 127.38, 1)], box=None, er=(1, 4, 5)),
    "울산광역시": dict(pop=110, old=0.16, n=5, rural=1, spread=0.06,
                   hubs=[(35.54, 129.31, 1)], box=(35.40, 35.70, 128.95, 129.25), er=(1, 2, 4)),
    "세종특별자치시": dict(pop=39, old=0.11, n=3, rural=2, spread=0.04,
                     hubs=[(36.48, 127.29, 1)], box=(36.45, 36.70, 127.15, 127.35), er=(0, 1, 2)),
    "경기도": dict(pop=1370, old=0.16, n=31, rural=6, spread=0.12,
                hubs=[(37.27, 127.03, 3), (37.39, 126.93, 2), (37.65, 126.83, 2), (37.74, 127.05, 1),
                      (37.00, 127.10, 1), (37.20, 126.83, 1)],
                box=(37.00, 38.20, 126.70, 127.70), er=(5, 25, 30)),
    "강원특별자치도": dict(pop=152, old=0.25, n=8, rural=10, spread=0.06,
                     hubs=[(37.88, 127.73, 1), (37.34, 127.92, 1), (37.75, 128.88, 1), (38.20, 128.59, 0.4)],
                     box=(37.10, 38.30, 127.30, 129.10), er=(2, 4, 10)),
    "충청북도": dict(pop=159, old=0.21, n=7, rural=8, spread=0.06,
                  hubs=[(36.64, 127.49, 2), (36.99, 127.93, 1)],
                  box=(36.10, 37.20, 127.30, 128.30), er=(1, 3, 8)),
    "충청남도": dict(pop=213, old=0.21, n=8, rural=8, spread=0.06,
                  hubs=[(36.81, 127.11, 2), (36.78, 127.00, 1), (36.60, 126.66, 0.6)],
                  box=(36.00, 37.00, 126.30, 127.50), er=(1, 3, 10)),
    "전북특별자치도": dict(pop=174, old=0.25, n=6, rural=9, spread=0.06,
                     hubs=[(35.82, 127.15, 2), (35.95, 126.71, 1), (35.97, 126.96, 1)],
                     box=(35.40, 36.10, 126.50, 127.80), er=(1, 3, 9)),
    "전라남도": dict(pop=179, old=0.27, n=7, rural=14, spread=0.06,
                  hubs=[(34.81, 126.39, 1), (34.76, 127.66, 1), (34.95, 127.49, 1)],
                  box=(34.30, 35.30, 126.20, 127.80), er=(1, 4, 12)),
    "경상북도": dict(pop=254, old=0.26, n=9, rural=14, spread=0.07,
                  hubs=[(36.02, 129.34, 1.5), (36.12, 128.34, 1.5), (35.83, 128.73, 0.8), (36.57, 128.73, 0.6)],
                  box=(35.70, 37.00, 128.00, 129.45), er=(2, 4, 12)),
    "경상남도": dict(pop=323, old=0.22, n=10, rural=10, spread=0.07,
                  hubs=[(35.23, 128.68, 3), (35.18, 128.08, 1), (35.23, 128.88, 1), (34.85, 128.43, 0.5)],
                  box=(34.80, 35.70, 127.70, 129.10), er=(2, 5, 12)),
    "제주특별자치도": dict(pop=67, old=0.19, n=4, rural=3, spread=0.04,
                     hubs=[(33.50, 126.53, 2), (33.25, 126.56, 1)],
                     box=(33.25, 33.50, 126.20, 126.90), er=(1, 2, 4)),
}

GRADES = ["권역응급의료센터", "지역응급의료센터", "지역응급의료기관"]

regions, ers = [], []
for sido, c in SIDO.items():
    short = {"충청북도": "충북", "충청남도": "충남", "경상북도": "경북", "경상남도": "경남",
             "전북특별자치도": "전북", "전라남도": "전남"}.get(sido, sido[:2])
    hubs = np.array([(h[0], h[1]) for h in c["hubs"]])
    w = np.array([h[2] for h in c["hubs"]], dtype=float)
    w = w / w.sum()

    pts, kinds = [], []
    # 1) 도시 지역: 중심점 주변에 모여 있음
    for _ in range(c["n"]):
        k = rng.choice(len(hubs), p=w)
        lat, lon = hubs[k] + rng.normal(0, c["spread"], 2)
        pts.append((lat, lon)); kinds.append("도시")
    # 2) 농어촌 지역: 넓은 범위에 흩어져 있음
    for _ in range(c["rural"]):
        b = c["box"]
        pts.append((rng.uniform(b[0], b[1]), rng.uniform(b[2], b[3]))); kinds.append("농어촌")

    # 인구 배분: 도시 지역에 훨씬 많이
    raw = np.array([rng.lognormal(3.0, 0.4) if k == "도시" else rng.lognormal(1.3, 0.5) for k in kinds])
    pops = np.round(raw / raw.sum() * c["pop"] * 10000).astype(int)

    for i, ((lat, lon), kind, pop) in enumerate(zip(pts, kinds, pops), start=1):
        old = c["old"] + (0.10 if kind == "농어촌" else 0) + rng.normal(0, 0.03)
        old = float(np.clip(old, 0.08, 0.50))
        regions.append(dict(sido=sido, sigungu=f"{short}가상{'군' if kind == '농어촌' else '구'}{i:02d}",
                            area_type=kind, lat=round(lat, 4), lon=round(lon, 4),
                            pop=int(pop), pop65=int(pop * old),
                            pop014=int(pop * float(np.clip(0.16 - old * 0.25 + rng.normal(0, 0.01), 0.04, 0.2)))))

    # 응급의료기관: 인구가 많은 도시 지역 근처에 배치
    city_idx = [i for i, k in enumerate(kinds) if k == "도시"]
    city_w = pops[city_idx] / pops[city_idx].sum()
    n_er = 0
    hub_pts = [hubs[k] for k in np.argsort(-w)]          # 큰 도시부터
    for grade, cnt in zip(GRADES, c["er"]):
        for j in range(cnt):
            if grade == "권역응급의료센터":            # 권역센터는 가장 큰 중심 도시에
                base = hub_pts[0]; jit = 0.03
            elif j < len(hub_pts):                     # 지역센터·지역기관은 도시마다 최소 1곳
                base = hub_pts[j]; jit = 0.02
            elif grade == "지역응급의료기관" and kinds.count("농어촌") and rng.random() < 0.5:
                base = np.array(pts[rng.choice([i for i, k in enumerate(kinds) if k == "농어촌"])]); jit = 0.02
            else:
                base = np.array(pts[rng.choice(city_idx, p=city_w)]); jit = 0.03
            lat, lon = base + rng.normal(0, jit, 2)
            n_er += 1
            ers.append(dict(name=f"{short}가상병원{n_er:02d}", sido=sido, grade=grade,
                            lat=round(lat, 4), lon=round(lon, 4)))

os.makedirs("data/sample", exist_ok=True)
pd.DataFrame(regions).to_csv("data/sample/regions.csv", index=False, encoding="utf-8-sig")
pd.DataFrame(ers).to_csv("data/sample/er.csv", index=False, encoding="utf-8-sig")
print(f"지역 {len(regions)}개, 응급의료기관 {len(ers)}개 생성 → data/sample/")
