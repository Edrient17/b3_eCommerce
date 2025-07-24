from flask import Flask, render_template, request, redirect, url_for, flash, session
import pandas as pd
import pymysql
from recommend import recommend_products   # 연관 추천 로직 불러오기
from datetime import datetime
import delay_prediction 
import pymysql.cursors
import os
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
app.secret_key = 'your_secret_key'

def get_connection():
    return pymysql.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

# 상품 데이터 로드
product_df = pd.read_csv("./data/Product_Data_2차전처리완료.csv", encoding="euc-kr")
product_df = product_df.dropna(subset=['제품 당 구매빈도'])
product_df = product_df.sort_values(by='제품 당 구매빈도', ascending=False)

# 열 이름 영문으로 통일
product_df.rename(columns={
    '제품번호': 'product_id',
    '물품명': 'name',
    '제품별 평균금액': 'price'
}, inplace=True)

def attach_weight_to_name(row):
    if pd.notna(row.get('상품중량')):
        return f"{row['name']} {row['상품중량']}"
    return row['name']

product_df['name'] = product_df.apply(attach_weight_to_name, axis=1)

preferred_products = {
    ('여', 20): ['100021009V2_765', '10002158V2_128', '100022325V2_1733', '100021507V2_1148', '100021071V2_806'],
    ('남', 20): ['100022325V2_1733', '100021754V2_1316', '100022020V2_1513', '10002158V2_128', '100022453V2_1839'],
    ('여', 30): ['100021071V2_806', '10002158V2_128', '10002577V2_444', '10002165V2_132', '10002408V2_312'],
    ('남', 30): ['10002158V2_128', '10002294V2_222', '100021746V2_1311', '100022058V2_1542', '100021754V2_1316'],
    ('여', 40): ['100021420V2_1091', '10002531V2_408', '10002500V2_384', '100021663V2_1244', '100021301V2_987'],
    ('남', 40): ['100022317V2_1725', '10002723V2_563', '10002531V2_408', '100021746V2_1311', '10002408V2_312'],
    ('여', 50): ['100021489V2_1136', '10002939V2_714', '100022074V2_1550', '100021663V2_1244', '100021714V2_1286'],
    ('남', 50): ['100021755V2_1317', '100021621V2_1209', '100021507V2_1148', '100021064V2_803', '100021611V2_1202']
}

@app.route('/organic')
def organic():
    new_brands = product_df[product_df['친환경전용관'] == 1][['product_id', 'name', 'price']]
    eco_products = product_df[(product_df['친환경'] == 1) & (product_df['친환경전용관'] != 1)][['product_id', 'name', 'price']]

    return render_template('organic.html',
                           new_brands=new_brands.to_dict(orient='records'),
                           products=eco_products.to_dict(orient='records'))


@app.route('/')
def home():
    username = session.get('username')
    user_id = session.get('user_id')

    top_banner_products = []
    banner_title = None
    banner_list = [
        {"label": "친환경 전용관", "filename": "organic_banner.jpg", "link": "/organic"},
        {"label": "등급별 혜택", "filename": "banner1.jpg"},
        {"label": "구독 프로모션 진행 중!", "filename": "banner2.jpg"},
        {"label": "친환경 제품 수요조사", "filename": "banner3.jpg"}
    ]

    if user_id:
        conn = get_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
        conn.close()

        if user:
            gender = user['gender']
            age_group = (int(user['age']) // 10) * 10
            recency = user.get('recency', 0)

            if recency > 90:
                banner_list.insert(0, {"label": "웰컴백 고객 할인!", "filename": "welcomeback.jpg"})
                
            product_ids = preferred_products.get((gender, age_group), [])
            top_banner_products = product_df[product_df['product_id'].isin(product_ids)][['product_id', 'name', 'price']].to_dict(orient='records')

            banner_title = f"당신을 위한 추천 상품. {age_group}대 {gender}성에게 인기!"

    top21 = product_df.head(21)[['product_id', 'name', 'price']].copy()

    return render_template(
        'main.html',
        username=username,
        banner_products=top_banner_products,
        banner_title=banner_title,
        products=top21.to_dict(orient='records'),
        banner_list=banner_list
    )


@app.route('/search')
def search():
    query = request.args.get('query', '').strip()

    if not query:
        flash('검색어를 입력해주세요.', 'error')
        return redirect(url_for('home'))

    # 대분류에서 검색
    filtered_df = product_df[product_df['물품대분류'].str.contains(query, case=False, na=False)]

    # 중분류별로 묶기
    grouped = {}
    for 중분류, group in filtered_df.groupby('물품중분류'):
        grouped[중분류] = group[['product_id', 'name', 'price']].to_dict(orient='records')

    return render_template('search.html', query=query, grouped_results=grouped)


@app.route('/product/<product_id>')
def product_detail(product_id):

    now = datetime.now()
    hour = now.hour
    if 2 <= hour < 6:
        time_segment = "새벽"
    elif 6 <= hour < 10:
        time_segment = "오전"
    elif 10 <= hour < 14:
        time_segment = "점심"
    elif 14 <= hour < 18:
        time_segment = "오후"
    elif 18 <= hour < 22:
        time_segment = "저녁"
    else:
        time_segment = "밤"
    day_of_week = ['월', '화', '수', '목', '금', '토', '일'][now.weekday()]

    product_row = product_df[product_df['product_id'] == product_id]
    if product_row.empty:
        return "상품을 찾을 수 없습니다.", 404

    product = product_row.iloc[0].to_dict()
    category = product['카테고리 분류']
    eco_flag = product['친환경']

    # 설명 생성
    친환경 = product.get("친환경", 0)
    신선 = product.get("신선", 0)
    대분류 = product.get("물품대분류", "")
    소분류 = product.get("물품소분류", "")

    설명 = []
    if 친환경 == 1 and 신선 == 1:
        설명.append("이 제품은 친환경 및 신선 식품입니다.")
    elif 친환경 == 1:
        설명.append("이 제품은 친환경 식품입니다.")
    elif 신선 == 1:
        설명.append("이 제품은 신선 식품입니다.")
    else:
        설명.append("이 제품은 일반 제품입니다.")

    # 설명 및 분류 저장
    product["설명"] = " ".join(설명)
    product["대분류"] = 대분류
    product["소분류"] = 소분류

    # 연관 제품 추천
    related_df = recommend_products(product_id)
    if related_df is not None:
        추천제품_ids = [item['product_id'] for item in related_df]
        related_products = product_df[product_df['product_id'].isin(추천제품_ids)][['product_id', 'name', 'price']].to_dict(orient='records')
    else:
        related_products = []

    # 배송 지연 예측 호출
    try:
        delay_prob = delay_prediction.predict_delay(
            time_segment=time_segment,
            day_of_week=day_of_week,
            category=category,
            eco_flag=eco_flag,
            fresh_flag=product['신선'],
            damaged_flag=product['파손/외관 손상 등 위험']
        )
    except Exception as e:
        print("❗예측 오류:", e)
        delay_prob = None

    is_best_brand = product.get('우수브랜드', 0) == 1  # True or False

    discount_names = ['오이', '콩나물', '양파']
    is_discount_item = any(name in product['name'] for name in discount_names)

    discount_price = None
    if is_discount_item:
        discount_price = round(product['price'] * 0.9)

    low_delay_products = []

    if delay_prob is not None and delay_prob >= 30:
        same_category_df = product_df[product_df['물품대분류'] == product['물품대분류']].copy()

        # 지연율 계산
        results = []
        for _, row in same_category_df.iterrows():
            if row['product_id'] == product['product_id']:
                continue  # 본인 제외

            try:
                pred_prob = delay_prediction.predict_delay(
                    time_segment=time_segment,
                    day_of_week=day_of_week,
                    category=row['카테고리 분류'],
                    eco_flag=row['친환경'],
                    fresh_flag=row['신선'],
                    damaged_flag=row['파손/외관 손상 등 위험']
                )
                if pred_prob <= 30:
                    results.append({
                        'product_id': row['product_id'],
                        'name': row['name'],
                        'price': row['price'],
                        'delay_prob': pred_prob
                    })
            except:
                continue

        # 가장 낮은 지연율 순으로 3개
        low_delay_products = sorted(results, key=lambda x: x['delay_prob'])[:3]

        print("🟡 지연율 높은 제품:", product['name'], "→ 지연율:", delay_prob)
        print("🔵 동일 카테고리 내 저지연 제품 후보 수:", len(low_delay_products))
        for item in low_delay_products:
            print("    🔹", item['name'], "지연율:", item['delay_prob'])

    return render_template(
        'product_detail.html',
        product=product,
        related_products=related_products,
        delay_prob=delay_prob,
        is_best_brand=is_best_brand,
        is_discount_item=is_discount_item,
        discount_price=discount_price,
        low_delay_products=low_delay_products
    )


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        try:
            conn = get_connection()
            with conn.cursor() as cursor:
                sql = "SELECT * FROM users WHERE username = %s AND password = %s"
                cursor.execute(sql, (username, password))
                user = cursor.fetchone()

            if user:
                session['user_id'] = user['id']
                session['username'] = user['username']
                flash('로그인 성공!', 'success')
                return redirect(url_for('home'))
            else:
                flash('아이디 또는 비밀번호가 잘못되었습니다.', 'error')
                return redirect(url_for('login'))
        finally:
            conn.close()
    return render_template('login.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        gender = request.form['gender']
        age = request.form['age']
        card = request.form['card']
        region = request.form['region']
        subregion = request.form['subregion']

        if not username or not password or not gender or not age:
            flash('모든 필드를 입력해주세요.', 'error')
            return redirect(url_for('signup'))

        try:
            conn = get_connection()
            with conn.cursor() as cursor:
                sql = '''
                    INSERT INTO users (username, password, gender, age, card, region, subregion)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                '''
                cursor.execute(sql, (username, password, gender, age, card, region, subregion))
                conn.commit()
            flash('회원가입 성공! 로그인 해주세요.', 'success')
            return redirect(url_for('login'))
        except pymysql.err.IntegrityError:
            flash('이미 존재하는 사용자 이름입니다.', 'error')
            return redirect(url_for('signup'))
        finally:
            conn.close()
    return render_template('signup.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('로그아웃되었습니다.', 'success')
    return redirect(url_for('home'))


@app.route('/mypage', methods=['GET', 'POST'])
def mypage():
    if 'user_id' not in session:
        flash('로그인 후 이용해주세요.', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        user_id = session['user_id']
        try:
            conn = get_connection()
            with conn.cursor() as cursor:
                sql = "DELETE FROM users WHERE id = %s"
                cursor.execute(sql, (user_id,))
                conn.commit()
            session.clear()
            flash('정상적으로 탈퇴되었습니다.', 'success')
            return redirect(url_for('home'))
        finally:
            conn.close()
    return render_template('mypage.html', username=session['username'])


@app.route('/users')
def users():
    if 'user_id' not in session or session.get('username') != 'admin':
        flash('접근 권한이 없습니다.', 'error')
        return redirect(url_for('home'))

    conn = get_connection()
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT id, username, gender, age, card, region, subregion, recency FROM users
        """)
        user_list = cursor.fetchall()
    conn.close()

    return render_template('users.html', users=user_list)

from recommend import recommend_products, recommend_for_two  # 꼭 import!

@app.route('/wishlist')
def wishlist():
    print("🔎 장바구니 세션:", session.get('cart'))
    cart = session.get('cart', [])
    cart = list(map(str, cart))

    cart_items = product_df[product_df['product_id'].astype(str).isin(cart)].copy()
    cart_items.rename(columns={
        'product_id': 'product_id',
        'name': 'name',
        'price': 'price'
    }, inplace=True)

    # ✅ 추천 상품 로직
    recommendations = []
    if len(cart) == 1:
        recommendations = recommend_products(cart[0])
    elif len(cart) == 2:
        recommendations = recommend_for_two(cart[0], cart[1])

    return render_template('wishlist.html',
                           cart_items=cart_items.to_dict(orient='records'),
                           recommendations=recommendations)

@app.route('/handle_cart_action', methods=['POST'])
def handle_cart_action():
    action = request.form.get('action')
    
    if action == 'clear':
        session['cart'] = []
        session.modified = True
        flash("장바구니를 비웠습니다.")
    elif action == 'purchase':
        flash("🛍 구매 기능은 아직 구현되지 않았습니다.")
    
    return redirect(url_for('wishlist'))



@app.route('/add_to_cart/<product_id>', methods=['POST'])
def add_to_cart(product_id):
    # 세션에 장바구니가 없으면 초기화
    if 'cart' not in session:
        session['cart'] = []
    
    cart = session['cart']
    if product_id not in cart:
        cart.append(product_id)
        session['cart'] = cart
        flash('장바구니에 담겼습니다.')
    else:
        flash('이미 장바구니에 담겨있습니다.')

    return redirect(url_for('product_detail', product_id=product_id))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)