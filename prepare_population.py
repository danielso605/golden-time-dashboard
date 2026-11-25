"""
[실제 데이터 2-1] KOSIS 인구 파일 정리
--------------------------------------
KOSIS '행정구역(시군구)별/1세별 주민등록인구'에서 내려받은 파일(.xls 또는 .xlsx)을
대시보드용 표로 정리합니다.  (항목: 총인구수, 연령: 전체, 시점: 1개)

실행:  python prepare_population.py "다운로드한파일.xls"
결과:  data/raw/population.csv
       sido, sigungu, old_sido, pop(총인구), pop65(65세 이상), pop014(0~14세)

정리 규칙
  - 인구가 0인 '출장소' 줄은 제거
  - 일반구가 있는 시(수원시, 고양시 등)는 '수원시 장안구'처럼 구 단위로 나누고, 시 합계 줄은 제거
  - 전남광주통합특별시는 좌표 검색을 돕기 위해 옛 시도 이름(old_sido)을 함께 기록
"""
import os
import re
import sys
import pandas as pd

SIDO = ["서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "대전광역시", "울산광역시",
        "세종특별자치시", "경기도", "강원특별자치도", "충청북도", "충청남도", "전북특별자치도", "전라남도",
        "경상북도", "경상남도", "제주특별자치도", "전남광주통합특별시", "강원도", "전라북도"]
GWANGJU_GU = ["동구", "서구", "남구", "북구", "광산구"]   # 통합 전 광주광역시의 구


def read_kosis(path):
    """KOSIS 다운로드 파일 → (region, age, value) 표.
    KOSIS의 .xls 는 실제로는 XML(SpreadsheetML) 형식이라 직접 읽는다."""
    if path.lower().endswith(".xlsx"):
        raw = pd.read_excel(path, header=None)
        raw = raw.iloc[2:, :3]
        raw.columns = ["region", "age", "value"]
        raw["region"] = raw["region"].ffill()
        return raw
    text = open(path, "rb").read().decode("euc-kr", errors="replace")
    start = text.index('<Worksheet ss:Name="데이터">')
    end = text.find('<Worksheet ss:Name="메타정보">')
    text = text[start:end if end > 0 else None]
    rows = []
    for r in re.findall(r"<Row[^>]*>(.*?)</Row>", text, re.S):
        cells = re.findall(r"<Data[^>]*>(.*?)</Data>", r, re.S)
        if len(cells) == 5 and cells[0] != "행정구역(시군구)별":
            rows.append([cells[0], cells[1], cells[4]])        # 지역, 연령, 값
    return pd.DataFrame(rows, columns=["region", "age", "value"])


def age_num(a):
    m = re.match(r"(\d+)", str(a))
    return int(m.group(1)) if m else None


def main(path):
    df = read_kosis(path)
    df["value"] = pd.to_numeric(df["value"].astype(str).str.replace(",", ""), errors="coerce").fillna(0)
    df["n"] = df["age"].map(age_num)

    # KOSIS 표는 지역 순서대로 [계, 0세, 1세, …, 100세 이상] 이 반복되므로 '계' 줄로 지역을 나눈다
    df["block"] = (df["age"] == "계").cumsum()
    blocks = []
    for _, g in df.groupby("block", sort=True):
        blocks.append({
            "name": g["region"].iloc[0].strip(),
            "pop": int(g.loc[g["age"] == "계", "value"].iloc[0]),
            "pop65": int(g.loc[g["n"] >= 65, "value"].sum()),
            "pop014": int(g.loc[g["n"] <= 14, "value"].sum()),
        })

    out, sido, parent = [], None, None
    for i, b in enumerate(blocks):
        name = b["name"]
        if name == "전국":
            continue
        if name in SIDO and name != sido:          # 시도 합계 줄
            sido, parent = name, None
            continue
        if b["pop"] == 0 or "출장소" in name:      # 출장소 (인구 0) 제거
            continue
        nxt = blocks[i + 1]["name"] if i + 1 < len(blocks) else ""
        is_do = sido.endswith("도") and not sido.endswith("특별시")
        # 일반구가 딸린 시(예: 수원시 → 장안구 …)는 시 합계 줄을 건너뛰고 기억만 해 둔다
        if is_do and name.replace("(통합)", "").endswith("시") and nxt.endswith("구"):
            parent = name.replace("(통합)", "")
            continue
        if parent and is_do and name.endswith("구"):
            sigungu = f"{parent} {name}"
        else:
            parent = None
            sigungu = name
        old = ""
        if sido == "전남광주통합특별시":
            old = "광주광역시" if name in GWANGJU_GU else "전라남도"
        out.append(dict(sido=sido, sigungu=sigungu, old_sido=old,
                        pop=b["pop"], pop65=b["pop65"], pop014=b["pop014"]))

    res = pd.DataFrame(out)
    os.makedirs("data/raw", exist_ok=True)
    res.to_csv("data/raw/population.csv", index=False, encoding="utf-8-sig")
    total = [b for b in blocks if b["name"] == "전국"]
    print(f"시군구 {len(res)}곳 저장 → data/raw/population.csv")
    if total:
        print(f"검산: 전국 {total[0]['pop']:,}명 / 정리된 합계 {res['pop'].sum():,}명")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit('사용법: python prepare_population.py "KOSIS다운로드파일.xls"')
    main(sys.argv[1])
