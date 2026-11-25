"""
[실제 데이터 2-2] 시군구 좌표 찾기 (카카오 로컬 API)
---------------------------------------------------
prepare_population.py 로 만든 data/raw/population.csv 에 위도·경도를 붙입니다.

카카오 개발자센터(https://developers.kakao.com)에서 앱을 만들고 'REST API 키'를 받으세요.
    Windows(PowerShell):  $env:KAKAO_REST_KEY="키"; python prepare_regions.py
결과: data/processed/regions.csv
      (sido, sigungu, old_sido, area_type, lat, lon, pop, pop65, pop014)

※ 좌표는 시군구의 대표 지점(보통 구청·시청·군청 부근)입니다. 시군구 하나를 점 하나로
  보는 단순화이므로 보고서의 '한계점'에 적어 주세요.
"""
import os
import sys
import time
import pandas as pd
import requests

KEY = os.environ.get("KAKAO_REST_KEY")
URL = "https://dapi.kakao.com/v2/local/search/address.json"

# 최근 새로 생긴 구는 지도 서비스에 아직 없을 수 있어서, 대신 찾아볼 대표 지역
FALLBACK = {
    ("인천광역시", "제물포구"): "인천광역시 동구",
    ("인천광역시", "영종구"): "인천광역시 중구 운서동",
    ("인천광역시", "서해구"): "인천광역시 서구 석남동",
    ("인천광역시", "검단구"): "인천광역시 서구 마전동",
    ("경기도", "화성시 만세구"): "경기도 화성시 남양읍",
    ("경기도", "화성시 효행구"): "경기도 화성시 봉담읍",
    ("경기도", "화성시 병점구"): "경기도 화성시 진안동",
    ("경기도", "화성시 동탄구"): "경기도 화성시 오산동",
}


def geocode(q):
    r = requests.get(URL, params={"query": q}, headers={"Authorization": f"KakaoAK {KEY}"}, timeout=10)
    if r.status_code == 401:
        sys.exit("카카오 키 오류(401): REST API 키가 맞는지 확인하세요.")
    if r.status_code == 403:
        sys.exit("카카오 권한 오류(403): 앱 설정 > 제품 설정 > 카카오맵 사용을 ON으로 켜 주세요.")
    r.raise_for_status()
    docs = r.json().get("documents", [])
    if not docs:
        return None, None
    return float(docs[0]["y"]), float(docs[0]["x"])


def find(row):
    """여러 이름으로 차례대로 검색해 보고, 처음 찾은 좌표를 쓴다."""
    queries = [f"{row.sido} {row.sigungu}"]
    if isinstance(row.old_sido, str) and row.old_sido:
        queries.append(f"{row.old_sido} {row.sigungu}")          # 예: 광주광역시 광산구
    if (row.sido, row.sigungu) in FALLBACK:
        queries.append(FALLBACK[(row.sido, row.sigungu)])
    if " " in row.sigungu:                                      # 예: 수원시 장안구 → 수원시
        queries.append(f"{row.sido} {row.sigungu.split()[0]}")
    for q in queries:
        lat, lon = geocode(q)
        time.sleep(0.05)
        if lat is not None:
            return lat, lon, q
    return None, None, None


if __name__ == "__main__":
    if not KEY:
        sys.exit("환경변수 KAKAO_REST_KEY 가 없습니다. 파일 맨 위 설명을 확인하세요.")
    pop = pd.read_csv("data/raw/population.csv", encoding="utf-8-sig")
    pop["old_sido"] = pop["old_sido"].fillna("")

    lats, lons = [], []
    for row in pop.itertuples():
        lat, lon, used = find(row)
        print(f"{row.sido} {row.sigungu:12s} → {lat}, {lon}   (검색어: {used})")
        lats.append(lat); lons.append(lon)
    pop["lat"], pop["lon"] = lats, lons
    pop["area_type"] = pop["sigungu"].str.endswith("군").map({True: "농어촌", False: "도시"})

    miss = pop[pop["lat"].isna()]
    if len(miss):
        print("\n좌표를 못 찾은 지역 (보고서에 적거나 직접 좌표를 넣어 주세요):\n", miss[["sido", "sigungu"]])
    pop = pop.dropna(subset=["lat", "lon"])
    os.makedirs("data/processed", exist_ok=True)
    pop[["sido", "sigungu", "old_sido", "area_type", "lat", "lon", "pop", "pop65", "pop014"]].to_csv(
        "data/processed/regions.csv", index=False, encoding="utf-8-sig")
    print(f"\n완료: {len(pop)}개 시군구 → data/processed/regions.csv")
