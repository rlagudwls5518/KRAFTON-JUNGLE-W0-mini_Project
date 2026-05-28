import unittest
from unittest.mock import patch
import json
from flask import session
from bson import ObjectId
from werkzeug.security import generate_password_hash
import mongomock

# 테스트 대상인 Flask 앱 가져오기
from app import app, users_col, comments_col

class BalanceGameTestCase(unittest.TestCase):

    def setUp(self):
        """각 테스트 케이스가 실행되기 전에 호출되는 초기화 메서드"""
        # 1. Flask 테스트 클라이언트 및 컨텍스트 설정
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['JWT_SECRET_KEY'] = 'test-jwt-secret'
        self.app = app.test_client()
        self.ctx = app.app_context()
        self.ctx.push()

        # 2. PyMongo 컬렉션을 mongomock(인메모리 가짜 DB)으로 패치
        self.mongo_client = mongomock.MongoClient()
        self.db = self.mongo_client['balance_game']
        
        # 실제 전역 변수로 선언된 컬렉션을 Mock 객체로 교체
        self.patcher1 = patch('app.users_col', self.db['users'])
        self.patcher2 = patch('app.comments_col', self.db['comments'])
        self.mock_users = self.patcher1.start()
        self.mock_comments = self.patcher2.start()

    def tearDown(self):
        """각 테스트가 끝난 후 자원을 정리하는 메서드"""
        self.patcher1.stop()
        self.patcher2.stop()
        self.ctx.pop()

    # -------------------------------------------------------------------------
    # 1. 회원가입 기능 테스트
    # -------------------------------------------------------------------------
    def test_signup_success(self):
        """요구사항: 필수 정보를 입력하면 회원가입이 정상적으로 완료되어야 한다."""
        response = self.app.post('/signup', data={
            'username': 'tester1',
            'password': 'password123',
            'nickname': '테스터닉네임',
            'age': '25',
            'intro': '안녕하세요'
        })
        
        # 회원가입 성공 시 로그인 페이지로 리다이렉트(/login) 되는지 검증
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('/login'))
        
        # DB에 데이터가 정상적으로 들어갔는지 검증
        user = self.mock_users.find_one({'username': 'tester1'})
        self.assertIsNotNone(user)
        self.assertEqual(user['nickname'], '테스터닉네임')

    def test_signup_duplicate_username(self):
        """요구사항: 이미 존재하는 아이디로 가입을 시도하면 가입이 거부되어야 한다."""
        # 기존 유저 미리 삽입
        self.mock_users.insert_one({
            'username': 'tester1',
            'password': generate_password_hash('password123'),
            'nickname': '기존닉네임'
        })

        response = self.app.post('/signup', data={
            'username': 'tester1', # 중복 아이디
            'password': 'newpassword',
            'nickname': '새로운닉네임'
        })

        # 가입 실패 후 다시 회원가입 페이지로 튕기는지 검증
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('/signup'))

    # -------------------------------------------------------------------------
    # 2. 로그인 기능 테스트
    # -------------------------------------------------------------------------
    def test_login_success(self):
        """요구사항: 올바른 비밀번호를 입력하면 세션이 생성되고 JWT 토큰이 발급되어야 한다."""
        # 유저 데이터 준비
        self.mock_users.insert_one({
            'username': 'tester1',
            'password': generate_password_hash('password123'),
            'nickname': '테스터닉네임'
        })

        # JSON 방식으로 로그인 요청
        response = self.app.post('/login', 
                                 data=json.dumps({'username': 'tester1', 'password': 'password123'}),
                                 content_type='application/json')

        self.assertEqual(response.status_code, 200)
        
        # 응답 데이터에 JWT access_token이 포함되어 있는지 검증
        data = json.loads(response.data)
        self.assertIn('access_token', data)

        # Flask 세션에 유저 정보가 정상적으로 구워졌는지 검증
        with self.app.session_transaction() as sess:
            self.assertEqual(sess['username'], 'tester1')

    # -------------------------------------------------------------------------
    # 3. 비즈니스 로직(익명 댓글) 검증 테스트
    # -------------------------------------------------------------------------
    def test_add_comment_anonymous_stores_actual_writer_id(self):
        """
        [자소서 연계 핵심 요구사항 검증]
        요구사항: 익명 댓글을 작성하더라도 내부 검증을 위해 
        데이터베이스에는 항상 실제 작성자의 writer_id가 기록되어야 한다.
        """
        # 1. 가짜 유저 생성 및 세션/JWT 인증 우회를 위한 세팅
        user_id = ObjectId()
        self.mock_users.insert_one({
            '_id': user_id,
            'username': 'tester1',
            'nickname': '개발자형진'
        })

        # 2. JWT 토큰 발급 후 헤더에 주입하기 위해 로그인 절차 선행
        login_res = self.app.post('/login', 
                                  data=json.dumps({'username': 'tester1', 'password': 'password123'}),
                                  content_type='application/json')
        access_token = json.loads(login_res.data).get('access_token')
        headers = {'Authorization': f'Bearer {access_token}'}

        # 3. 익명 옵션(is_anonymous=True)으로 댓글 작성 요청
        card_id = str(ObjectId())
        comment_data = {
            'comment': '이것은 익명으로 작성하는 밸런스 토크 댓글입니다.',
            'is_anonymous': True
        }

        response = self.app.post(f'/cards/{card_id}/comment', 
                                 data=json.dumps(comment_data),
                                 content_type='application/json',
                                 headers=headers)

        self.assertEqual(response.status_code, 200)

        # 4. 데이터베이스 검증 (AI의 로직 허점을 잡아낸 핵심 부분)
        saved_comment = self.mock_comments.find_one({'card_id': card_id})
        self.assertIsNotNone(saved_comment)
        
        # 깐깐한 검증 1: 겉으로 보이는 닉네임은 반드시 '익명'이어야 함
        self.assertEqual(saved_comment['nickname'], '익명')
        
        # 깐깐한 검증 2: 내부 'writer_id' 필드는 None이 아니라 실제 유저 고유 ID여야 함 (삭제 권한 보장)
        self.assertEqual(saved_comment['writer_id'], str(user_id))
        self.assertTrue(saved_comment['is_anonymous'])


if __name__ == '__main__':
    unittest.main()