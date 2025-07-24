import pandas as pd
from itertools import combinations
from collections import Counter
import ast

# 데이터 로드
product_df = pd.read_csv("./data/Product_Data_2차전처리완료.csv", encoding="euc-kr")
sales_df = pd.read_csv("./data/Sales_Data_2차전처리완료.csv", encoding="euc-kr")
order_summary_df = pd.read_csv("./data/주문_요약_분석(6번째).csv", encoding="utf-8")

# 이름 매핑
product_name_map = product_df.set_index('제품번호')['물품명'].to_dict()

# 주문 제품 리스트화
order_summary_df['최종_구매_제품'] = order_summary_df['최종_구매_제품'].apply(ast.literal_eval)
order_products = order_summary_df['최종_구매_제품'].apply(lambda x: list(set([item[0] for item in x])))
num_orders = len(order_products)

# 연관 규칙 계산
single_counter = Counter()
pair_counter = Counter()
for products in order_products:
    unique = set(products)
    single_counter.update(unique)
    if len(unique) >= 2:
        pair_counter.update(combinations(sorted(unique), 2))

# 연관규칙 DataFrame 생성
records = []
for (a, b), ab_count in pair_counter.items():
    support_ab = ab_count / num_orders
    support_a = single_counter[a] / num_orders
    support_b = single_counter[b] / num_orders
    confidence_a_to_b = support_ab / support_a if support_a else 0
    confidence_b_to_a = support_ab / support_b if support_b else 0
    lift = support_ab / (support_a * support_b) if support_a * support_b else 0

    records.append({
        '제품A': a, '제품B': b, '공동구매횟수': ab_count,
        'Support': support_ab,
        'Confidence(A→B)': confidence_a_to_b,
        'Confidence(B→A)': confidence_b_to_a,
        'Lift': lift
    })

association_df = pd.DataFrame(records)

association_df['제품A'] = association_df['제품A'].astype(str)
association_df['제품B'] = association_df['제품B'].astype(str)

# 추천 함수
def recommend_products(product_id, topn=5):
    df = association_df[
        ((association_df['제품A'] == product_id) | (association_df['제품B'] == product_id)) &
        (association_df['Lift'] >= 1)
    ].copy()

    if df.empty:
        return []

    df['추천제품'] = df.apply(
        lambda row: row['제품B'] if row['제품A'] == product_id else row['제품A'],
        axis=1
    )
    df = df[df['추천제품'] != product_id]
    df = df.sort_values(by='공동구매횟수', ascending=False).head(topn)

    result = product_df[product_df['제품번호'].isin(df['추천제품'])][['제품번호', '물품명', '제품별 평균금액']]
    result.rename(columns={
        '제품번호': 'product_id',
        '물품명': 'name',
        '제품별 평균금액': 'price'
    }, inplace=True)

    return result.to_dict(orient='records')

def recommend_for_two(product_id1, product_id2, topn=5):
    rec1 = recommend_products(product_id1)
    rec2 = recommend_products(product_id2)

    # product_id만 추출해서 교집합
    set1 = {item['product_id'] for item in rec1}
    set2 = {item['product_id'] for item in rec2}
    common_ids = set1 & set2

    # 교집합이 없다면 union 사용
    if not common_ids:
        common_ids = set1 | set2

    # 해당 제품들의 상세 정보 추출
    result = product_df[product_df['제품번호'].astype(str).isin(common_ids)].copy()
    result = result[['제품번호', '물품명', '제품별 평균금액']]
    result.rename(columns={'제품번호': 'product_id', '물품명': 'name', '제품별 평균금액': 'price'}, inplace=True)

    return result.head(topn).to_dict(orient='records')
