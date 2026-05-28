from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, session, send_file
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo import MongoClient
from datetime import datetime
from bson import ObjectId
from gridfs import GridFS
from io import BytesIO
import os

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = os.environ.get("SESSION_SECRET", "your-secret-key-fallback")
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['JWT_SECRET_KEY'] = os.environ.get("JWT_SECRET_KEY", "your-jwt-secret-key-fallback")
jwt = JWTManager(app)

# MongoDB connection
client = MongoClient('mongodb://test:test@3.36.128.55',27017)
db = client['balance_game']
users_col = db['users']
cards_col = db['cards']
comments_col = db['comments']
fs = GridFS(db)

@app.before_request
def require_login():
    if request.endpoint in ('login', 'signup', 'static', 'index', 'token_login', 'profile_image'):
        return
    if request.path.startswith('/profile_image/'):
        return
    if 'username' not in session:
        return redirect(url_for('login'))


@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        nickname = request.form.get('nickname', '').strip()
        age = request.form.get('age')
        intro = request.form.get('intro')
        profile_file = request.files.get('profile')

        if not username or not password:
            flash('아이디와 비밀번호를 입력해주세요.')
            return redirect(url_for('signup'))

        if users_col.find_one({'username': username}):
            flash('이미 존재하는 아이디입니다.')
            return redirect(url_for('signup'))
        if nickname and users_col.find_one({'nickname': nickname}):
            flash('이미 존재하는 별명입니다.')
            return redirect(url_for('signup'))

        profile_file_id = None
        if profile_file and profile_file.filename and allowed_file(profile_file.filename):
            profile_file_id = fs.put(profile_file, filename=secure_filename(profile_file.filename))

        hashed_pw = generate_password_hash(password)
        users_col.insert_one({
            'username': username,
            'password': hashed_pw,
            'nickname': nickname,
            'age': int(age) if age else None,
            'intro': intro,
            'profile_file_id': profile_file_id
        })
        flash('회원가입이 완료되었습니다.')
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/profile_image/<user_id>')
def profile_image(user_id):
    try:
        user = users_col.find_one({'_id': ObjectId(user_id)})
        if not user or not user.get('profile_file_id'):
            # Return default profile image
            return send_file('static/default-profile.png', mimetype='image/png')

        file_id = user['profile_file_id']
        image_data = fs.get(file_id).read()
        return send_file(BytesIO(image_data), mimetype='image/png')
    except:
        return send_file('static/default-profile.png', mimetype='image/png')

# 통합 -> 로그인
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # JSON 또는 form 방식 모두 지원
        data = request.get_json(silent=True)
        if data:
            username = data.get('username')
            password = data.get('password')
        else:
            username = request.form.get('username')
            password = request.form.get('password')

        user = users_col.find_one({'username': username})
        if not user or not password or not check_password_hash(user['password'], password):
            return jsonify({"message": "아이디 또는 비밀번호가 올바르지 않습니다."}), 401

        access_token = create_access_token(identity=username)
        session['username'] = username
        session['user_id'] = str(user['_id'])
        return jsonify(access_token=access_token), 200

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# 통합) 게시판(SSR) -> 검색/익명/비익명/댓글/페이지네이션
@app.route('/board', methods=['GET', 'POST'])
def board_page():
    page = int(request.args.get('page', 1))
    per_page = 10
    skip = (page - 1) * per_page

    if request.method == 'POST':
        # 게시글 작성 처리
        opt1 = request.form.get('option1')
        opt2 = request.form.get('option2')
        is_anonymous = request.form.get('is_anonymous', '0') == '1'   # ⭐️익명 여부
        writer = session.get('username')
        user = users_col.find_one({'username': writer})
        
        if not opt1 or not opt2 or not user:
            flash("모든 항목을 입력해주세요.")
            return redirect(url_for('board_page'))
        
        
        new_card = {
            'option1': opt1,
            'option2': opt2,
            'result1': 0,
            'result2': 0,
            'likes': 0,
            'created_at': datetime.utcnow(),
            'votes': {},
            'liked_by': [],
            'is_anonymous': is_anonymous,      # 익명 여부
            'writer_id': str(user['_id']),    # ★ 항상 저장 (익명/비익명 무관)
        }

        #익명 여부에 따라 작성자 정보 저장
        if is_anonymous:
            new_card['writer'] = '익명'    # 익명일 때 작성자 이름
        else:
            new_card['writer'] = user.get('nickname', '익명')

       
        cards_col.insert_one(new_card)
        flash("작성이 완료되었습니다.")
        return redirect(url_for('board_page'))

    # 검색 기능
    search_query = request.args.get('query', '').strip()
    search_type = request.args.get('type', 'all')

    filter_liked = request.args.get('filterLiked', '0') == '1'
    username = session.get('username')
    user = users_col.find_one({'username': username}) if username else None
    user_id = str(user['_id']) if user else None

    query = {}
    if search_query:
        if search_type == 'option1':
            query['option1'] = {'$regex': search_query, '$options': 'i'}
        elif search_type == 'option2':
            query['option2'] = {'$regex': search_query, '$options': 'i'}
        elif search_type == 'writer':
            query['writer'] = {'$regex': search_query, '$options': 'i'}
        else:
            query['$or'] = [
                {'option1': {'$regex': search_query, '$options': 'i'}},
                {'option2': {'$regex': search_query, '$options': 'i'}},
                {'writer': {'$regex': search_query, '$options': 'i'}}
            ]

    if filter_liked and user_id:
        query['liked_by'] = user_id
    
    total_cards = cards_col.count_documents(query)
    total_pages = (total_cards + per_page - 1) // per_page
    cards = list(cards_col.find(query).sort('created_at', -1).skip(skip).limit(per_page))

    # ➕ 카드별로 댓글 추가
    for card in cards:
        card['_id'] = str(card['_id'])  # ObjectId를 문자열로 변환
        card['comments'] = list(comments_col.find({'card_id': card['_id']}).sort('created_at', 1))

    return render_template('board.html', cards=cards, page=page, total_pages=total_pages, search_query=search_query,search_type=search_type
    )
#
@app.route('/cards/<card_id>/comment/<comment_id>/delete', methods=['DELETE'])
@jwt_required()
def delete_comment(card_id, comment_id):
    current_user = get_jwt_identity()
    user_doc = users_col.find_one({'username': current_user})
    user_id = str(user_doc['_id']) if user_doc else None

    comment = comments_col.find_one({'_id': ObjectId(comment_id)})
    if not comment:
        return jsonify({'error': '댓글을 찾을 수 없습니다.'}), 404

    # 익명이든 아니든 작성자 본인만 삭제 가능
    if str(comment.get('writer_id')) != user_id:
        return jsonify({'error': '권한이 없습니다.'}), 403

    comments_col.delete_one({'_id': ObjectId(comment_id)})
    return jsonify({'message': '댓글 삭제 성공'})





# 통합) API: 카드 목록/생성 
@app.route('/cards', methods=['GET', 'POST'])
@jwt_required()
def cards_api():
    if request.method == 'POST':
        data = request.get_json(silent=True) or request.form
        opt1 = data.get('option1')
        opt2 = data.get('option2')

        #통합 추가1
        is_anonymous = str(data.get('is_anonymous', '0')) == '1'
        current_user = get_jwt_identity()
        user = users_col.find_one({'username': current_user})

        if not opt1 or not opt2:
            return jsonify({'error': '모든 항목을 입력해주세요.'}), 400
        
        #통합 추가2
        new_card = {
            'option1': opt1,
            'option2': opt2,
            'result1': 0,
            'result2': 0,
            'likes': 0,
            'created_at': datetime.utcnow(),
            'votes': {},
            'liked_by': [],
            'is_anonymous': is_anonymous
        }
        if is_anonymous:
            new_card['writer'] = '익명'
        else:
            new_card['writer'] = user.get('nickname', '익명')
            new_card['writer_id'] = str(user['_id'])

        res = cards_col.insert_one(new_card)
        return jsonify({'_id': str(res.inserted_id)}), 201

    # GET - 카드 목록 (검색/좋아요 필터링 포함)
    search_query = request.args.get('search', '').strip()
    search_type = request.args.get('search_type', 'all')
    filter_liked = request.args.get('filterLiked', 'false').lower() == 'true'

    #통합 변경
    current_user = get_jwt_identity()
    current_user_doc = users_col.find_one({'username': current_user})
    current_user_id = str(current_user_doc['_id']) if current_user_doc else None

    query = {}
    if search_query:
        if search_type == 'option1':
            query['option1'] = {'$regex': search_query, '$options': 'i'}
        elif search_type == 'option2':
            query['option2'] = {'$regex': search_query, '$options': 'i'}
        elif search_type == 'writer':
            query['writer'] = {'$regex': search_query, '$options': 'i'}
        else:
            query['$or'] = [
                {'option1': {'$regex': search_query, '$options': 'i'}},
                {'option2': {'$regex': search_query, '$options': 'i'}},
                {'writer': {'$regex': search_query, '$options': 'i'}}
            ]
    if filter_liked and current_user_id:
        query['liked_by'] = current_user_id

    raw_cards = cards_col.find(query).sort('created_at', -1)
    cards = []
    for c in raw_cards:
        cid = str(c['_id'])
        user_vote = c.get('votes', {}).get(current_user_id)
        user_liked = current_user_id in c.get('liked_by', [])
        cards.append({
            '_id': cid,
            'writer': c.get('writer', '익명'),
            'writer_id': str(c.get('writer_id', '')) if not c.get('is_anonymous') else None,
            'option1': c['option1'],
            'option2': c['option2'],
            'votes1': c.get('result1', 0),
            'votes2': c.get('result2', 0),
            'likes': c.get('likes', 0),
            'hasVoted': user_vote,
            'hasLiked': user_liked,
            'is_anonymous': c.get('is_anonymous', False),
            'created_at': c['created_at'].isoformat()
        })

    return jsonify({'cards': cards})


@app.route('/cards/<card_id>/vote', methods=['POST'])
@jwt_required()
def vote_card(card_id):
    data = request.get_json() or {}
    opt = str(data.get('option'))
    if opt not in ('1', '2'):
        return jsonify({'error': 'invalid option'}), 400
    
    current_user = get_jwt_identity()
    current_user_doc = users_col.find_one({'username': current_user})
    current_user_id = str(current_user_doc['_id']) if current_user_doc else None
    
    if not current_user_id:
        return jsonify({'error': 'User not found'}), 404
    
    card = cards_col.find_one({'_id': ObjectId(card_id)})
    if not card:
        return jsonify({'error': 'Card not found'}), 404
    
    votes = card.get('votes', {})
    prev_vote = votes.get(current_user_id)
    
    # Remove previous vote if exists
    if prev_vote:
        cards_col.update_one(
            {'_id': ObjectId(card_id)}, 
            {'$inc': {f'result{prev_vote}': -1}}
        )
    
    # Add new vote if different from previous
    if prev_vote != opt:
        cards_col.update_one(
            {'_id': ObjectId(card_id)}, 
            {
                '$inc': {f'result{opt}': 1},
                '$set': {f'votes.{current_user_id}': opt}
            }
        )
        voted = opt
    else:
        # Same vote clicked - remove it
        cards_col.update_one(
            {'_id': ObjectId(card_id)}, 
            {'$unset': {f'votes.{current_user_id}': ""}}
        )
        voted = None
    
    # Get updated card
    updated_card = cards_col.find_one({'_id': ObjectId(card_id)})
    return jsonify({
        'result1': updated_card.get('result1', 0),
        'result2': updated_card.get('result2', 0),
        'voted': voted
    }),200

@app.route('/cards/<card_id>/like', methods=['POST'])
@jwt_required()
def like_card(card_id):
    current_user = get_jwt_identity()
    current_user_doc = users_col.find_one({'username': current_user})
    current_user_id = str(current_user_doc['_id']) if current_user_doc else None
    
    if not current_user_id:
        return jsonify({'error': 'User not found'}), 404
    
    card = cards_col.find_one({'_id': ObjectId(card_id)})
    if not card:
        return jsonify({'error': 'Card not found'}), 404
    
    liked_by = card.get('liked_by', [])
    
    if current_user_id in liked_by:
        # Unlike
        cards_col.update_one(
            {'_id': ObjectId(card_id)}, 
            {
                '$inc': {'likes': -1},
                '$pull': {'liked_by': current_user_id}
            }
        )
        liked = False
    else:
        # Like
        cards_col.update_one(
            {'_id': ObjectId(card_id)}, 
            {
                '$inc': {'likes': 1},
                '$addToSet': {'liked_by': current_user_id}
            }
        )
        liked = True
    
    # Get updated card
    updated_card = cards_col.find_one({'_id': ObjectId(card_id)})
    return jsonify({
        'likes': updated_card.get('likes', 0),
        'liked': liked
    }), 200

#통랍)댓글기능
@app.route('/cards/<card_id>/comment', methods=['POST'])
@jwt_required()
def add_comment(card_id):
    user = get_jwt_identity()
    user_doc = users_col.find_one({'username': user})

    # ⭐️ 익명 데이터 처리
    data = request.get_json()
    content = data.get("comment")
    is_anonymous = data.get("is_anonymous") == True or data.get("is_anonymous") == "1"  # JS에서 bool/문자 다 받을 수 있음

    if is_anonymous:
        nickname = "익명"
        writer_id = None
    else:
        nickname = user_doc['nickname'] if user_doc else '익명'
        writer_id = str(user_doc['_id']) if user_doc else None

    if not content:
        return jsonify({'error': '댓글 내용을 입력하세요.'}), 400
    
    comments_col.insert_one({
        'card_id': card_id,
        'nickname': nickname,
        'writer_id': writer_id,
        'is_anonymous': is_anonymous,
        'content': content,
        'created_at': datetime.utcnow()
    })
    return jsonify({'message': '댓글 등록 성공'})
   

@app.route('/cards/<card_id>/comments', methods=['GET'])
@jwt_required()
def get_comments(card_id):
    comment_list = list(comments_col.find({'card_id': card_id}).sort('created_at', 1))
    for c in comment_list:
        c['_id'] = str(c['_id'])  # ObjectId 문자열로 변환
        c['created_at'] = c['created_at'].isoformat()   
    return jsonify({'comments': comment_list})


@app.route('/cards/<card_id>/delete', methods=['DELETE'])
@jwt_required()
def delete_card(card_id):
    current_user = get_jwt_identity()
    current_user_doc = users_col.find_one({'username': current_user})
    current_user_id = str(current_user_doc['_id']) if current_user_doc else None
    
    card = cards_col.find_one({'_id': ObjectId(card_id)})
    if not card:
        return jsonify({'error': 'Card not found'}), 404
    
    # writer_id가 내 id와 같으면 삭제 허용
    if card.get('writer_id') != current_user_id:
        return jsonify({'error': 'Unauthorized'}), 403

    cards_col.delete_one({'_id': ObjectId(card_id)})
    return jsonify({'message': 'Card deleted successfully'})


@app.route('/popular-card')
@jwt_required()
def popular_card():
    # Get the most liked card
    popular_card = cards_col.find_one({'likes': {'$gte': 1}},sort=[('likes', -1)])
    
    if not popular_card:
        return jsonify({'card': None})
    
    current_user = get_jwt_identity()
    current_user_doc = users_col.find_one({'username': current_user})
    current_user_id = str(current_user_doc['_id']) if current_user_doc else None
    
    user_vote = popular_card.get('votes', {}).get(current_user_id)
    user_liked = current_user_id in popular_card.get('liked_by', [])
    
    card_data = {
        '_id': str(popular_card['_id']),
        'writer': popular_card.get('writer', '익명'),
        'writer_id': str(popular_card.get('writer_id', '')),
        'option1': popular_card['option1'],
        'option2': popular_card['option2'],
        'votes1': popular_card.get('result1', 0),
        'votes2': popular_card.get('result2', 0),
        'likes': popular_card.get('likes', 0),
        'hasVoted': user_vote,
        'hasLiked': user_liked,
        'created_at': popular_card['created_at'].isoformat()
    }
    
    return jsonify({'card': card_data})

@app.route('/cards')
def show_cards():
    per_page = 10
    page = int(request.args.get('page', 1))

    skip = (page - 1) * per_page
    total_cards = cards_col.count_documents({})
    total_pages = (total_cards + per_page - 1) // per_page

    cards = list(cards_col.find().sort('_id', -1).skip(skip).limit(per_page))
    return render_template('cards.html', cards=cards, page=page, total_pages=total_pages)


@app.route('/user/<user_id>')
@jwt_required()
def get_user_profile(user_id):
    try:
        user = users_col.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        profile_data = {
            '_id': str(user['_id']),
            'username': user['username'],
            'nickname': user.get('nickname', '익명'),
            'age': user.get('age'),
            'intro': user.get('intro', ''),
            'has_profile_image': user.get('profile_file_id') is not None
        }
        
        return jsonify(profile_data)
    except:
        return jsonify({'error': 'Invalid user ID'}), 400

@app.route('/user/me')
@jwt_required()
def get_current_user():
    current_user = get_jwt_identity()
    user = users_col.find_one({'username': current_user})
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    profile_data = {
        '_id': str(user['_id']),
        'username': user['username'],
        'nickname': user.get('nickname', '익명'),
        'age': user.get('age'),
        'intro': user.get('intro', ''),
        'has_profile_image': user.get('profile_file_id') is not None
    }
    
    return jsonify(profile_data)

@app.route('/user/<user_id>/recent-votes')
@jwt_required()
def get_user_recent_votes(user_id):
    try:
        user = users_col.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'error': 'User not found'}), 404

        recent_cards = cards_col.find({f'votes.{str(user["_id"])}': {'$exists': True}}).sort('created_at', -1).limit(5)
        result = []
        for card in recent_cards:
            user_vote = card.get('votes', {}).get(str(user['_id']))
            result.append({
                'option1': card.get('option1'),
                'option2': card.get('option2'),
                'votes1': card.get('result1', 0),
                'votes2': card.get('result2', 0),
                'voted': user_vote,
                'created_at': card.get('created_at').isoformat()
            })
        return jsonify({'votes': result})
    except:
        return jsonify({'error': 'Invalid user ID'}), 400

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=True)