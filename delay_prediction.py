import numpy as np
import pandas as pd
from xgboost import XGBClassifier
from sklearn.preprocessing import LabelEncoder
import joblib
import os

# 모델 훈련용 함수 (최초 1회 실행 후 저장만 하면 됨)
def train_and_save_model():
    df = pd.read_csv("./data/리스크예측_주문취소_배송지연.csv", encoding="euc-kr")
    df = df[df['배송상태'] != '취소'].copy()

    label_encoders = {}
    for col in ['주문시간대', '주문요일', '배송상태', '카테고리 분류', '친환경']:
        le = LabelEncoder()
        df[col] = le.fit_transform(df[col])
        label_encoders[col] = le

    X = df.drop(columns=['배송상태', '구매금액', '제품별 평균금액', '제품 당 구매빈도'])
    y = df['배송상태']

    model = XGBClassifier(use_label_encoder=False, eval_metric='mlogloss', random_state=42)
    model.fit(X, y)

    joblib.dump(model, "delay_model.pkl")
    joblib.dump(label_encoders, "label_encoders.pkl")


def predict_delay(time_segment, day_of_week, category, eco_flag, fresh_flag, damaged_flag, threshold=0.3):
    try:
        model = joblib.load("delay_model.pkl")
        label_encoders = joblib.load("label_encoders.pkl")
    except FileNotFoundError:
        print("❌ 모델 파일 또는 인코더 파일이 없습니다. 먼저 train_and_save_model()을 실행하세요.")
        return None

    try:
        X_input = pd.DataFrame([{
            '주문시간대': label_encoders['주문시간대'].transform([time_segment])[0],
            '주문요일': label_encoders['주문요일'].transform([day_of_week])[0],
            '카테고리 분류': label_encoders['카테고리 분류'].transform([category])[0],
            '친환경': eco_flag,
            '신선': fresh_flag,
            '파손/외관 손상 등 위험': damaged_flag
        }])
    except Exception as e:
        print("❗예측 입력값 인코딩 실패:", e)
        return None

    try:
        y_proba = model.predict_proba(X_input)
        delay_class_index = list(label_encoders['배송상태'].classes_).index('지연')
        delay_prob = y_proba[0][delay_class_index]
        return round(delay_prob * 100, 1)  # 확률(%) 반환
    except Exception as e:
        print("❗예측 실패:", e)
        return None
